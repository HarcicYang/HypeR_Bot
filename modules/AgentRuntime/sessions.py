"""Main and System context session management."""

import json
import os
import re
import time
import traceback
import uuid
from typing import Any, Literal, cast

from hyperot import configurator, hyperogger
from hyperot.listener import Actions

from modules.AgentRuntime.core import AgentCore
from modules.AgentRuntime.models import HISTORY_PATH, SESSIONS_PATH, SYSTEM_PATH, AgentEvent, SessionKey
from modules.AgentRuntime.profiles import AgentProfile, load_profiles
from modules.AgentRuntime.prompts import ROLE_PROMPT

config = configurator.BotConfig.get("hyper-bot")
logger = hyperogger.Logger()
logger.set_level(config.log_level)


def _load_profiles() -> dict[str, AgentProfile]:
    return load_profiles(ROLE_PROMPT)


def _save_profile_name_to_config(name: str) -> None:
    with open("config.json", encoding="utf-8") as f:
        cfg = json.load(f)
    cfg.setdefault("others", {})["agent_profile"] = name
    with open("config.json", "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


class SessionManager:
    @staticmethod
    def _sort_context(item: tuple[SessionKey, AgentCore]) -> str:
        return item[0].value

    def __init__(self, owner: Any, actions: Actions) -> None:
        from modules.AgentTools.memory_store import MemoryStore

        self.owner = owner
        self.actions = actions
        self.cores: dict[SessionKey, AgentCore] = {}
        self.shared_memory = MemoryStore(
            "./temps/agent_memory", limit=int(config.others.get("agent_memory_limit") or 500)
        )
        self.system_core = self._create_core(SessionKey("system", 0), role="system")
        self._migrate_legacy_history()

    def _create_core(self, key: SessionKey, role: Literal["main", "system"] = "main") -> AgentCore:
        os.makedirs(key.directory, exist_ok=True)
        core = AgentCore(
            bot_api=self.actions,
            key=cast(str, config.others.get("openai_key")),
            model=cast(str, config.others.get("openai_model")),
            base_url=cast(str, config.others.get("openai_endpoint") or ""),
            name="system" if role == "system" else "main",
            history_path=os.path.join(key.directory, "history.json"),
            tasks_path=os.path.join(key.directory, "tasks.json"),
            memory_path="./temps/agent_memory",
            role=role,
            session_key=key,
            session_manager=self,
            shared_memory=self.shared_memory,
        )
        self.cores[key] = core
        return core

    def _migrate_legacy_history(self) -> None:
        marker = os.path.join(SYSTEM_PATH, "legacy_history_imported")
        if os.path.exists(marker) or not os.path.isfile(HISTORY_PATH):
            return
        try:
            with open(HISTORY_PATH, encoding="utf-8") as f:
                legacy = json.load(f)
            if isinstance(legacy, list) and len(legacy) > 1:
                event = AgentEvent(
                    type="legacy_global_history",
                    scene_type="system",
                    scene_id=0,
                    source="migration",
                    payload={
                        "path": HISTORY_PATH,
                        "message_count": len(legacy),
                        "history": legacy,
                        "note": "旧版全局历史，仅供 System Context 参考，不自动注入任何 Main 上下文。",
                    },
                )
                self.system_core.history.append(
                    {
                        "role": "user",
                        "content": json.dumps({"event": event.to_dict()}, ensure_ascii=False),
                    }
                )
                os.makedirs(os.path.dirname(self.system_core.history_path), exist_ok=True)
                with open(self.system_core.history_path, "w", encoding="utf-8") as f:
                    json.dump(self.system_core.history, f, indent=2, ensure_ascii=False)
            with open(marker, "w", encoding="utf-8") as f:
                f.write(str(int(time.time())))
        except (OSError, json.JSONDecodeError):
            logger.warning("迁移旧 Agent 全局历史失败: " + traceback.format_exc())

    def _discover_contexts(self) -> None:
        if not os.path.isdir(SESSIONS_PATH):
            return
        for dirname in os.listdir(SESSIONS_PATH):
            match = re.fullmatch(r"(group|private)_(\d+)", dirname)
            if match is None:
                continue
            scene_type = cast(Literal["group", "private"], match.group(1))
            key = SessionKey(scene_type, int(match.group(2)))
            if key not in self.cores:
                self.get_core(scene_type, key.scene_id)

    def get_core(self, scene_type: Literal["group", "private"], scene_id: int) -> AgentCore:
        key = SessionKey(scene_type, scene_id)
        core = self.cores.get(key)
        if core is None:
            core = self._create_core(key)
            core.sub_manager = self.owner.sub_manager
        return core

    def core_for_key(self, key: SessionKey) -> AgentCore:
        if key.scene_type == "system":
            return self.system_core
        return self.get_core(cast(Literal["group", "private"], key.scene_type), key.scene_id)

    async def list_contexts(self) -> str:
        self._discover_contexts()
        lines = ["Main 上下文:"]
        main_items = sorted(
            ((key, core) for key, core in self.cores.items() if key.scene_type != "system"),
            key=self._sort_context,
        )
        if not main_items:
            return "Main 上下文: (空)"
        for key, core in main_items:
            lines.append(f"- {key.value}: {len(core.history_turns())} 轮, {len(core.history)} 条历史")
        return "\n".join(lines)

    async def context_status(self, target: str) -> str:
        try:
            key = SessionKey.parse(target)
        except ValueError as e:
            return repr(e)
        core = self.core_for_key(key)
        return (
            f"上下文 {key.value}: {len(core.history_turns())} 轮, {len(core.history)} 条历史, "
            f"状态={'处理中' if core.working else '空闲'}"
        )

    async def read_context(self, target: str, count: int, anchor: int | None, direction: str) -> str:
        try:
            key = SessionKey.parse(target)
        except ValueError as e:
            return repr(e)
        if key.scene_type == "system":
            return "System Context 历史不向 Main 上下文读取"
        if not 1 <= count <= 50:
            return "count 必须在 1 到 50 之间"
        if direction not in ("backward", "forward"):
            return "direction 必须为 backward 或 forward"
        turns = self.core_for_key(key).history_turns()
        if not turns:
            return f"上下文 {key.value} 暂无会话轮次"
        pivot = len(turns) if anchor is None else anchor
        if not 1 <= pivot <= len(turns):
            return f"anchor 必须在 1 到 {len(turns)} 之间"
        if direction == "backward":
            start, end = max(0, pivot - count), pivot
        else:
            start, end = pivot - 1, min(len(turns), pivot - 1 + count)
        payload = [{"turn": i + 1, "messages": turns[i]} for i in range(start, end)]
        return json.dumps(
            {"context": key.value, "total_turns": len(turns), "turns": payload},
            ensure_ascii=False,
        )

    async def send_context(
        self,
        source: SessionKey,
        target: str,
        content: str,
        kind: str,
        request_id: str | None,
    ) -> str:
        try:
            target_key = SessionKey.parse(target)
        except ValueError as e:
            return repr(e)
        if not content.strip():
            return "通信内容不能为空"
        if kind not in ("message", "request", "reply"):
            return f"未知上下文消息类型: {kind}"
        if kind == "request":
            request_id = request_id or f"ctx_{uuid.uuid4().hex}"
        elif kind == "reply" and not request_id:
            return "回复必须提供 request_id"
        payload = {
            "kind": kind,
            "request_id": request_id,
            "source": source.value,
            "target": target_key.value,
            "content": content,
        }
        event = AgentEvent(
            type="context_message",
            scene_type=target_key.scene_type,
            scene_id=target_key.scene_id,
            payload=payload,
            source=source.value,
        )
        target_core = self.core_for_key(target_key)
        target_core.inject_notice(event)
        await target_core.save()
        label = f"，request_id={request_id}" if request_id else ""
        return f"已从 {source.value} 投递到 {target_key.value}{label}"

    async def request_profile_switch(self, source: SessionKey, name: str) -> str:
        if name not in _load_profiles():
            return f"人设「{name}」不存在"
        request_id = f"sys_{uuid.uuid4().hex}"
        event = AgentEvent(
            type="system_request",
            scene_type="system",
            scene_id=0,
            source=source.value,
            payload={
                "request_id": request_id,
                "operation": "switch_profile",
                "source": source.value,
                "name": name,
                "instruction": ("调用 switch_profile 执行全局人设切换，再用 context_send 向 source 返回执行结果。"),
            },
        )
        self.system_core.inject_notice(event)
        await self.system_core.save()
        return f"系统上下文已受理人设切换请求 #{request_id}"

    async def apply_global_profile(self, name: str) -> str:
        profiles = _load_profiles()
        profile = profiles.get(name)
        if profile is None:
            return f"人设「{name}」不存在,可用: {', '.join(profiles.keys()) or '(无)'}"
        config.others["agent_profile"] = name
        _save_profile_name_to_config(name)
        for core in self.cores.values():
            if core.role != "main":
                continue
            await core._acquire_processing_slot()
            try:
                core._apply_profile_prompt(profile)
                core._refresh_tools()
                await core.save()
            finally:
                await core._release_processing_slot()
        return f"已切换到人设「{name}」并刷新全部 Main 上下文"

    async def request_summary(self, source: SessionKey, target: SessionKey) -> str:
        turns = self.core_for_key(target).history_turns()
        if not turns:
            return f"上下文 {target.value} 暂无可总结内容"
        request_id = f"sys_{uuid.uuid4().hex}"
        event = AgentEvent(
            type="system_request",
            scene_type="system",
            scene_id=0,
            source=source.value,
            payload={
                "request_id": request_id,
                "operation": "summarize_context",
                "source": source.value,
                "target": target.value,
                "through_turn": len(turns),
                "instruction": (
                    "分页调用 context_read 读取目标上下文截至 through_turn 的原始轮次，生成完整摘要，"
                    "调用 context_replace_summary 写回，再用 context_send 向 source 返回结果。"
                ),
            },
        )
        self.system_core.inject_notice(event)
        await self.system_core.save()
        return f"系统上下文已受理总结请求 #{request_id}"

    async def replace_summary(self, target: str, content: str, through_turn: int) -> str:
        try:
            key = SessionKey.parse(target)
        except ValueError as e:
            return repr(e)
        if key.scene_type == "system":
            return "不能替换 System Context 自身摘要"
        core = self.core_for_key(key)
        await core._acquire_processing_slot()
        try:
            user_indexes = [
                i
                for i, message in enumerate(core.history)
                if isinstance(message, dict) and message.get("role") == "user"
            ]
            if not 1 <= through_turn <= len(user_indexes):
                return f"through_turn 必须在 1 到 {len(user_indexes)} 之间"
            end = user_indexes[through_turn] if through_turn < len(user_indexes) else len(core.history)
            system_messages = [
                message for message in core.history if isinstance(message, dict) and message.get("role") == "system"
            ]
            system_message = (
                system_messages[0]
                if system_messages
                else {
                    "role": "system",
                    "content": core.system_prompt.replace("[ulist]", str(config.owner)),
                }
            )
            core.history = [
                system_message,
                {"role": "user", "content": "SYSTEM -- 先前会话截至指定轮次的总结 --"},
                {"role": "assistant", "content": content},
                *core.history[end:],
            ]
            await core.save()
        finally:
            await core._release_processing_slot()
        return f"已总结 {key.value} 截至第 {through_turn} 轮，并保留之后的新轮次"
