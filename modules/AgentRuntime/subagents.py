"""SubAgent lifecycle management."""

import asyncio
import os
import time
import traceback
from collections.abc import Callable
from typing import Any, Literal, cast

from hyperot import configurator, hyperogger
from hyperot.listener import Actions

from modules.AgentRuntime.models import AgentEvent, SessionKey

config = configurator.BotConfig.get("hyper-bot")
logger = hyperogger.Logger()
logger.set_level(config.log_level)


class SubAgent:
    def __init__(
        self,
        sub_id: int,
        name: str,
        prompt: str,
        scene_type: str,
        scene_id: int,
        perm_group: str,
        core: Any,
        owner_session: SessionKey | None,
    ) -> None:
        self.sub_id = sub_id
        self.name = name
        self.prompt = prompt
        self.scene_type = scene_type
        self.scene_id = scene_id
        self.perm_group = perm_group
        self.core = core
        self.owner_session = owner_session
        self.status = "running"
        self.created_at = int(time.time())


class SubAgentManager:
    """Manage SubAgent creation, destruction, status, and message delivery."""

    MAX_SUBAGENTS = 3

    def __init__(self, owner: Any, core_factory: Callable[..., Any]) -> None:
        self.owner = owner
        self.core_factory = core_factory
        self.subagents: dict[int, SubAgent] = {}
        self._next_id = 1

    def _notify(self, payload: dict[str, Any]) -> None:
        manager = self.owner.session_manager
        if manager is None:
            return
        if "owner_session" not in payload:
            source = str(payload.get("source") or "")
            for sub in self.subagents.values():
                if sub.core.name == source and sub.owner_session is not None:
                    payload["owner_session"] = sub.owner_session.value
                    break
        event = AgentEvent(type="subagent_status", scene_type="system", scene_id=0, payload=payload, source="sub")
        manager.system_core.inject_notice(event)
        logger.info(f"SubAgent 状态通知主 Agent: {payload}")

    async def create(
        self,
        name: str,
        prompt: str,
        scene_type: str,
        scene_id: int,
        perm_group: str = "member",
        owner_session: SessionKey | None = None,
    ) -> str:
        if len(self.subagents) >= self.MAX_SUBAGENTS:
            return f"SubAgent 数量已达上限({self.MAX_SUBAGENTS}),请先销毁其他 SubAgent 再创建"
        if scene_type not in ("group", "private"):
            return f"调用不合法：scene_type 必须为 group 或 private，当前为 {scene_type}"
        sub_id = self._next_id
        self._next_id += 1
        core = self.core_factory(
            bot_api=cast(Actions, self.owner.actions),
            key=cast(str, config.others.get("openai_key")),
            model=cast(str, config.others.get("openai_model")),
            base_url=cast(str, config.others.get("openai_endpoint") or ""),
            system_prompt=prompt,
            name=f"sub:{sub_id}",
            history_path=f"./temps/agent_sub_{sub_id}_history.json",
            tasks_path=f"./temps/agent_sub_{sub_id}_tasks.json",
            memory_path=f"./temps/agent_sub_{sub_id}_memory",
            notify_main=self._notify,
        )
        sub = SubAgent(sub_id, name, prompt, scene_type, scene_id, perm_group, core, owner_session)
        self.subagents[sub_id] = sub
        self._notify(
            {
                "action": "created",
                "sub_id": sub_id,
                "name": name,
                "scene": f"{scene_type}:{scene_id}",
                "owner_session": owner_session.value if owner_session is not None else None,
                "total": f"{len(self.subagents)}/{self.MAX_SUBAGENTS}",
            }
        )
        return f"SubAgent #{sub_id}「{name}」已创建并订阅 {scene_type}:{scene_id}(当前 {len(self.subagents)}/{self.MAX_SUBAGENTS})"

    async def destroy(self, sub_id: int) -> str:
        sub = self.subagents.pop(sub_id, None)
        if sub is None:
            return f"SubAgent #{sub_id} 不存在"
        # 优雅等待进行中的处理结束(上限 10s),再关闭 HTTP 连接池。
        for _ in range(100):
            if not sub.core.working and not sub.core._wakeup_pending:
                break
            await asyncio.sleep(0.1)
        try:
            await sub.core.aclose()
        except Exception:
            logger.warning("关闭 SubAgent 连接池失败: " + traceback.format_exc())
        for path in (
            sub.core.history_path,
            sub.core.tasks_path,
            sub.core.memory_path + ".json",
            sub.core.memory_path + ".npz",
        ):
            if os.path.exists(path):
                os.remove(path)
        self._notify(
            {
                "action": "destroyed",
                "sub_id": sub_id,
                "name": sub.name,
                "owner_session": sub.owner_session.value if sub.owner_session is not None else None,
                "total": f"{len(self.subagents)}/{self.MAX_SUBAGENTS}",
            }
        )
        return f"SubAgent #{sub_id}「{sub.name}」已销毁(当前 {len(self.subagents)}/{self.MAX_SUBAGENTS})"

    def list(self) -> str:
        if not self.subagents:
            return f"暂无 SubAgent(0/{self.MAX_SUBAGENTS})"
        lines = [f"SubAgent 列表({len(self.subagents)}/{self.MAX_SUBAGENTS}):"]
        for sub_id, sub in self.subagents.items():
            lines.append(
                f"#{sub_id} 「{sub.name}」[{sub.status}] 订阅 {sub.scene_type}:{sub.scene_id} 创建于 {sub.created_at}"
            )
        return "\n".join(lines)

    def status(self, sub_id: int) -> str:
        sub = self.subagents.get(sub_id)
        if sub is None:
            return f"SubAgent #{sub_id} 不存在"
        return (
            f"SubAgent #{sub_id}「{sub.name}」\n"
            f"状态: {sub.status} | 订阅: {sub.scene_type}:{sub.scene_id} | 权限: {sub.perm_group}\n"
            f"创建于: {sub.created_at} | 历史消息数: {len(sub.core.history)}"
        )

    async def feed(self, sub_id: int, content: str, perm_group: str = "member") -> str:
        sub = self.subagents.get(sub_id)
        if sub is None:
            return f"SubAgent #{sub_id} 不存在"
        asyncio.create_task(
            sub.core.event_handler(
                event=content,
                ev_type=cast(Literal["group", "private"], sub.scene_type),
                scene_id=sub.scene_id,
                perm_group=perm_group,
            )
        )
        return f"已向 SubAgent #{sub_id}「{sub.name}」投喂消息"
