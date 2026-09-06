"""Agent core runtime implementation."""

import asyncio
import base64
import contextlib
import copy
import inspect
import json
import os
import re
import time
import traceback
import uuid
from typing import Any, Literal, cast
from urllib.parse import urlparse

import openai
from hyperot import configurator, hyperogger, segments
from hyperot.events import *
from hyperot.listener import Actions
from hyperot.protocol.builder import OneBotEventBuilder, OneBotJsonMessageBuilder
from openai import AsyncOpenAI

import ModuleClass
from modules.AgentRuntime.capture import CaptureActions as _CaptureActions
from modules.AgentRuntime.dsml import parse_embedded_tool_calls as _parse_embedded_tool_calls
from modules.AgentRuntime.models import HISTORY_PATH, REPORT_TIMEOUT, TASKS_PATH, AgentEvent, SessionKey
from modules.AgentRuntime.profiles import AgentProfile as _AgentProfile
from modules.AgentRuntime.profiles import load_profiles as _runtime_load_profiles
from modules.AgentRuntime.prompts import (
    OUTPUT_RULE,
    ROLE_PROMPT,
    SUBAGENT_RULE,
    SYSTEM_CONTEXT_PROMPT,
)
from modules.AgentRuntime.prompts import (
    build_system_prompt as _build_system_prompt,
)
from modules.AgentRuntime.prompts import (
    web_search_note as _web_search_note,
)
from modules.AgentRuntime.tool_text import build_tools_section as _build_tools_section
from modules.AgentTools.registry import ToolContext, ToolRegistry

config = configurator.BotConfig.get("hyper-bot")
logger = hyperogger.Logger()
logger.set_level(config.log_level)

_concurrency_limit: int = int(config.others.get("agent_max_concurrency") or 0)
_semaphore: asyncio.Semaphore | None = None

# Google 官方文档给出的占位签名,用于历史消息兜底
# https://ai.google.dev/gemini-api/docs/thought-signatures
GEMINI_DUMMY_SIGNATURE = "context_engineering_is_the_way_to_go"

# 命中即视为 Google 的 OpenAI 兼容端点
_GOOGLE_HOST_MARKERS = (
    "generativelanguage.googleapis.com",
    "aiplatform.googleapis.com",
    "googleapis.com",
    "gemini.googleapis.com",
)


def _acquire_semaphore() -> asyncio.Semaphore | None:
    global _semaphore
    if _concurrency_limit <= 0:
        return None
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(_concurrency_limit)
    return _semaphore


def _load_profiles() -> dict[str, _AgentProfile]:
    return _runtime_load_profiles(ROLE_PROMPT)


def _save_profile_name_to_config(name: str) -> None:
    with open("config.json", encoding="utf-8") as f:
        cfg = json.load(f)
    cfg.setdefault("others", {})["agent_profile"] = name
    with open("config.json", "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


async def timer(interval: int, ev: asyncio.Event) -> None:
    await asyncio.sleep(interval)
    ev.set()


class AgentCore:
    def __init__(
            self,
            bot_api: Actions,
            key: str,
            model: str,
            base_url: str = "",
            system_prompt: str | None = None,
            name: str = "main",
            history_path: str = HISTORY_PATH,
            tasks_path: str = TASKS_PATH,
            memory_path: str = "./temps/agent_memory",
            notify_main: Any = None,
            sub_manager: Any = None,
            role: Literal["main", "sub", "system"] | None = None,
            session_key: SessionKey | None = None,
            session_manager: Any = None,
            shared_memory: Any = None,
    ) -> None:
        self.bot_api = bot_api
        self.model = model
        self.name = name
        self.role: Literal["main", "sub", "system"] = role or ("main" if name == "main" else "sub")
        self.session_key = session_key
        self.session_manager = session_manager
        self._base_prompt = system_prompt
        self.tools: list[Any] = ToolRegistry.schema(role=self.role)
        self.system_prompt = self._build_system_prompt_for_role()
        self.history_path = history_path
        self.tasks_path = tasks_path
        self.memory_path = memory_path
        self.notify_main = notify_main
        self.sub_manager = sub_manager

        self.extra = {
            'extra_body': {
                # "google": {
                #     "thinking_config": {
                #         "include_thoughts": True
                #     }
                # }
            }
        }
        if base_url:
            self._oai = AsyncOpenAI(api_key=key, base_url=base_url)
        else:
            self._oai = AsyncOpenAI(api_key=key)
        self.history: list[Any] = [
            {"role": "system", "content": self.system_prompt.replace("[ulist]", str(config.owner))}
        ]
        try:
            with open(self.history_path, encoding="utf-8") as f:
                data = json.load(f)
            # 历史中的 DSML/XML 伪工具调用文本会污染后续请求(可能触发 400),载入时清掉。
            if isinstance(data, list):
                for message in data:
                    if not isinstance(message, dict) or message.get("role") != "assistant":
                        continue
                    raw = message.get("content")
                    if isinstance(raw, str) and "<" in raw:
                        cleaned, _, _ = _parse_embedded_tool_calls(raw)
                        if cleaned != raw:
                            logger.warning("已从历史 assistant 消息中清除 DSML/XML 伪工具调用文本")
                            message["content"] = cleaned
            # 旧版本可能把 system 文本存成 role=user 的脏条目(开头是 system 提示词),
            # 会导致 history[0] 不是 system:切换人设被 guard 跳过、且提示词会被当作
            # user 消息发给模型,让模型沿用旧人设。这里识别并清掉,再保证第一条是 system。
            while (
                    data
                    and isinstance(data[0], dict)
                    and data[0].get("role") != "system"
                    and str(data[0].get("content", "")).startswith("# 角色")
            ):
                data.pop(0)
            if not data or not isinstance(data[0], dict) or data[0].get("role") != "system":
                data.insert(0, {"role": "system", "content": self.system_prompt.replace("[ulist]", str(config.owner))})
            else:
                data[0]["content"] = self.system_prompt.replace("[ulist]", str(config.owner))
            self.history = data
        except (FileNotFoundError, IndexError, KeyError, json.JSONDecodeError):
            pass
        self.chat_tasks: list[str] = []
        try:
            with open(self.tasks_path, encoding="utf-8") as f:
                self.chat_tasks = json.load(f)
        except FileNotFoundError:
            pass
        # RAG 长期记忆(BGE 向量检索 + BM25 降级)
        from modules.AgentTools.memory_store import MemoryStore

        self.memory = shared_memory or MemoryStore(
            self.memory_path, limit=int(config.others.get("agent_memory_limit") or 500)
        )
        self._injected_memory = ""  # 本次事件自动注入的相关记忆(请求时附加到 system,不落盘)
        self.working = False
        self.pending_notices: list[AgentEvent] = []
        self.report_waiters: dict[str, asyncio.Future[Any]] = {}
        self._report_seq = 0
        self._wakeup_pending = False
        self._notice_count = 0
        self._tool_loop_active = False
        self._pending_profile_switch: tuple[str, _AgentProfile, str] | None = None
        self._pending_summary: str | None = None
        self._auto_summary_task: asyncio.Task[None] | None = None
        self.last_used: float = 0.0
        self._evicting = False
        self._state_lock = asyncio.Lock()
        self._idle_event = asyncio.Event()
        self._idle_event.set()
        self.api_mode = cast(str, config.others.get("agent_api") or "chat")
        self.reasoning_effort = str(config.others.get("agent_reasoning_effort") or "low")
        self.web_search = self.role != "system" and bool(config.others.get("agent_web_search", True))
        self.native_multimodal = self.role != "system" and bool(config.others.get("agent_native_multimodal", True))

    # -- runtime 接口(供工具经 ToolContext.runtime 调用) --

    async def summarize_history(self, content: str) -> str:
        """消息总结统一入口:工具回合中延后,外部调用取得处理权后应用。"""
        if self._tool_loop_active:
            self._pending_summary = content
            return "(总结已受理,当前工具回合结束后生效)"
        await self._acquire_processing_slot()
        try:
            return await self._apply_summary(content)
        finally:
            await self._release_processing_slot()

    async def _apply_summary(self, content: str) -> str:
        """实际替换历史;调用方必须确认当前没有未完成的 tool call。"""
        self.history = [
            {"role": "system", "content": self.system_prompt.replace("[ulist]", str(config.owner))},
            {"role": "user", "content": "SYSTEM -- 先前消息的全部总结 --"},
            {"role": "assistant", "content": content},
        ]
        logger.info("更新消息总结： \n" + content)
        await self.save()
        return "(无返回)"

    async def _finish_pending_summary(self) -> None:
        """在当前工具批次完成后应用待处理摘要。"""
        content = self._pending_summary
        self._pending_summary = None
        if content is not None:
            await self._apply_summary(content)

    async def clear_history(self, content: str) -> str:
        """兼容旧名;新调用请使用 summarize_history。"""
        return await self.summarize_history(content)

    def _apply_profile_prompt(self, profile: _AgentProfile) -> None:
        """把指定人设写入 system_prompt 与 history 的第一条 system 消息(不落盘)。"""
        self.system_prompt = _build_system_prompt(profile)
        new_content = self.system_prompt.replace("[ulist]", str(config.owner))
        for i, m in enumerate(self.history):
            if isinstance(m, dict) and m.get("role") == "system":
                self.history[i]["content"] = new_content
                break
        else:
            self.history.insert(0, {"role": "system", "content": new_content})

    def _history_text_for_summary(self) -> str:
        """把当前 history 压成可供 LLM 摘要的紧凑文本(跳过 system,截断长消息)。"""
        lines: list[str] = []
        for m in self.history:
            if not isinstance(m, dict) or m.get("role") == "system":
                continue
            role = str(m.get("role"))
            content = str(m.get("content", ""))
            if role == "tool":
                content = f"工具结果: {content}"
            elif role == "assistant" and m.get("tool_calls"):
                names = [
                    str(tc.get("function", {}).get("name", "")) for tc in m.get("tool_calls") if isinstance(tc, dict)
                ]
                content = content or f"调用工具: {', '.join(names)}"
            content = re.sub(r"\s+", " ", content).strip()
            if content:
                lines.append(f"{role}: {content[:1200]}")
        return "\n".join(lines)

    def _fallback_summary(self, text: str) -> str:
        lines = text.splitlines()
        tail = lines[-120:]
        return "上下文自动总结不可用,降级为原文摘录:\n" + "\n".join(line[:500] for line in tail)

    async def _generate_history_summary(self) -> str:
        """让 LLM 自动压缩当前历史;失败时降级为原文摘录。"""
        text = self._history_text_for_summary()
        if not text.strip():
            return "（当前无对话历史）"
        try:
            resp = await asyncio.wait_for(
                self._oai.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "你是对话上下文压缩器。请把下面的QQ机器人聊天历史压缩为一段简洁中文摘要，"
                                "保留关键话题、事件、人物关系、未完成任务与需要跟进的事项。"
                                "不要寒暄，直接输出摘要。"
                            ),
                        },
                        {"role": "user", "content": text[-16000:]},
                    ],
                    temperature=0.2,
                    max_tokens=2000,
                    extra_body=self.extra
                ),
                timeout=90,
            )
            summary = (resp.choices[0].message.content or "").strip()
            if summary:
                return summary
        except Exception:
            logger.warning("上下文自动总结失败,降级为原文摘录: " + traceback.format_exc())
        return self._fallback_summary(text)

    async def summarize_current_context(self) -> str:
        """命令入口:等待全局 Core 空闲,让 LLM 总结当前上下文并替换历史。"""
        await self._acquire_processing_slot()
        try:
            summary = await self._generate_history_summary()
            await self._apply_summary(summary)
            return "上下文已由 LLM 自动总结"
        finally:
            await self._release_processing_slot()

    def _history_chars(self) -> int:
        return sum(len(str(m.get("content", ""))) for m in self.history if isinstance(m, dict))

    def _maybe_schedule_auto_summary(self) -> None:
        """历史超过阈值时调度一次自动总结。

        只在锁外做检查与调度;总结任务内部通过 _acquire_processing_slot 抢锁,
        与事件处理天然串行。重复调用由 _auto_summary_task 去重。
        """
        max_chars = int(config.others.get("agent_max_history_chars") or 60000)
        if max_chars <= 0 or self._history_chars() < max_chars:
            return
        task = self._auto_summary_task
        if task is not None and not task.done():
            return
        self._auto_summary_task = asyncio.create_task(self._run_auto_summary())

    async def _run_auto_summary(self) -> None:
        logger.info("历史超过阈值，自动总结上下文")
        try:
            await self.summarize_current_context()
        except Exception:
            logger.error("自动总结失败: " + traceback.format_exc())

    async def _finish_profile_switch(self, name: str, profile: _AgentProfile, summary: str) -> str:
        """先写入自动总结,再应用新人设提示词;调用时已处于安全的历史边界。"""
        await self._apply_summary(summary)
        self._apply_profile_prompt(profile)
        await self.save()
        config.others["agent_profile"] = name  # 同步内存,使 _current_profile_name() 立即反映新值
        _save_profile_name_to_config(name)
        logger.info(f"人设已切换为「{name}」(切换前上下文已自动总结)")
        return f"已切换到人设「{name}」,切换前的上下文已自动总结"

    async def _finish_pending_profile_switch(self) -> None:
        """工具循环结束后应用延后的切换,确保 function_call 配对已经完整。"""
        pending = self._pending_profile_switch
        self._pending_profile_switch = None
        if pending is None:
            return
        name, profile, summary = pending
        try:
            await self._finish_profile_switch(name, profile, summary)
        except Exception:
            logger.error(traceback.format_exc())

    async def switch_profile(self, name: str, *, defer: bool | None = None) -> str:
        """人设切换统一入口；System Context 执行全局切换，Main 仅保留兼容路径。"""
        if self.role == "system":
            if self.session_manager is None:
                return "上下文管理器不可用"
            return await self.session_manager.apply_global_profile(name)
        profiles = _load_profiles()
        profile = profiles.get(name)
        if profile is None:
            return f"人设「{name}」不存在,可用: {', '.join(profiles.keys()) or '(无)'}"
        if defer is None:
            defer = self._tool_loop_active
        if defer:
            summary = await self._generate_history_summary()
            self._pending_profile_switch = (name, profile, summary)
            return f"人设「{name}」切换已受理,当前工具回合结束后生效(切换前的上下文会自动总结)"
        await self._acquire_processing_slot()
        try:
            summary = await self._generate_history_summary()
            return await self._finish_profile_switch(name, profile, summary)
        finally:
            await self._release_processing_slot()

    async def reset_history(self) -> str:
        """清空上下文,仅保留 system 提示词。"""
        await self._acquire_processing_slot()
        try:
            self.history = [
                {"role": "system", "content": self.system_prompt.replace("[ulist]", str(config.owner))},
            ]
            await self.save()
            return "上下文已清空"
        finally:
            await self._release_processing_slot()

    def context_info(self) -> str:
        """上下文状态概览:历史条数/字符数、任务列表。"""
        n = len(self.history)
        chars = sum(len(str(m.get("content", ""))) for m in self.history if isinstance(m, dict))
        tasks = self.chat_tasks
        head = f"上下文状态:共 {n} 条消息(约 {chars} 字符)"
        if tasks:
            head += "\n任务列表: " + "; ".join(f"[{i}]{t}" for i, t in enumerate(tasks))
        else:
            head += "\n任务列表: (空)"
        head += f"\n长期记忆: {self.memory.count()} 条{' (向量)' if self.memory.is_ready() else ' (BM25 降级)'}"
        return head

    # -- RAG 长期记忆(向量检索;embedding 为阻塞调用,统一走线程池) --

    async def mem_add(self, content: str) -> str:
        """添加一条长期记忆,返回条目 id。"""
        try:
            mem_id = await asyncio.to_thread(self.memory.add, content)
        except ValueError as e:
            return repr(e)
        return f"已记住 #{mem_id}"

    async def mem_query(self, content: str, top_k: int = 5) -> str:
        """语义检索相关记忆,返回 #id: text (score) 列表。"""
        try:
            rs = await asyncio.to_thread(self.memory.query, content, top_k)
        except Exception as e:
            return f"检索失败: {repr(e)}"
        if not rs:
            return "没有相关记忆"
        return "\n".join(f"#{self._mem_id_of(text)}: {text} ({score:.3f})" for text, score in rs)

    async def mem_list(self, limit: int = 20) -> str:
        """列出最近的记忆条目。"""
        items = await asyncio.to_thread(self.memory.list_all, limit)
        if not items:
            return "(记忆为空)"
        return "\n".join(f"#{e['id']}: {e['text']}" for e in items)

    async def mem_delete(self, mem_id: int) -> str:
        """删除指定 id 的记忆。"""
        ok = await asyncio.to_thread(self.memory.delete, mem_id)
        return f"已删除记忆 #{mem_id}" if ok else f"记忆 #{mem_id} 不存在"

    def _mem_id_of(self, text: str) -> int:
        for e in self.memory.entries:
            if e["text"] == text:
                return int(e["id"])
        return 0

    def mem_retrieve(self, query_text: str, top_k: int = 3) -> str:
        """同步检索相关记忆并格式化为注入段(供自动注入调用,阻塞)。"""
        if not query_text.strip():
            return ""
        try:
            rs = self.memory.query(query_text[:200], top_k)
        except Exception:
            return ""
        if not rs:
            return ""
        lines = [f"- {text[:100]}" for text, _ in rs]
        return "# 相关记忆\n" + "\n".join(lines)

    async def task_add(self, content: str) -> str:
        self.chat_tasks.append(content)
        return f"index={len(self.chat_tasks) - 1}"

    async def task_remove(self, index: int) -> str:
        self.chat_tasks.pop(index)
        return str(self.chat_tasks)

    async def task_list(self) -> str:
        return str(self.chat_tasks)

    # -- Main/System 上下文管理 --

    def history_turns(self) -> list[list[dict[str, Any]]]:
        """按 user 消息切分历史轮次；system 消息不计入轮次。"""
        turns: list[list[dict[str, Any]]] = []
        current: list[dict[str, Any]] = []
        for raw in self.history:
            if not isinstance(raw, dict) or raw.get("role") == "system":
                continue
            message = cast(dict[str, Any], raw)
            if message.get("role") == "user":
                if current:
                    turns.append(current)
                current = [message]
            elif current:
                current.append(message)
        if current:
            turns.append(current)
        return turns

    async def context_list(self) -> str:
        if self.session_manager is None:
            return "上下文管理器不可用"
        return await self.session_manager.list_contexts()

    async def context_status(self, target: str) -> str:
        if self.session_manager is None:
            return "上下文管理器不可用"
        return await self.session_manager.context_status(target)

    async def context_read(
            self, target: str, count: int = 5, anchor: int | None = None, direction: str = "backward"
    ) -> str:
        if self.session_manager is None:
            return "上下文管理器不可用"
        return await self.session_manager.read_context(target, count, anchor, direction)

    async def context_send(
            self, target: str, content: str, kind: str = "message", request_id: str | None = None
    ) -> str:
        if self.session_manager is None or self.session_key is None:
            return "当前 Core 不支持上下文通信"
        return await self.session_manager.send_context(self.session_key, target, content, kind, request_id)

    async def context_replace_summary(self, target: str, content: str, through_turn: int) -> str:
        if self.session_manager is None or self.role != "system":
            return "只有 System Context 可以替换上下文摘要"
        return await self.session_manager.replace_summary(target, content, through_turn)

    async def sys_ack(self, request_id: str, content: str) -> str:
        """System Context 专用:按 request_id 把系统请求处理结果回调给发起人(去重,仅一次)。"""
        if self.session_manager is None:
            return "上下文管理器不可用"
        return await self.session_manager.ack_sys_request(request_id, content)

    # -- 模块调用(run_module / list_modules / get_module_source) --

    @staticmethod
    def _find_module(name: str) -> type[ModuleClass.Module[Any]] | None:
        """按 module_name 优先、类名次之查找注册模块(忽略大小写)。

        注意:多个模块的类名都是 `Module`,必须优先按 module_name 匹配,
        否则类名匹配会命中错误模块。
        """
        name = name.strip().lower()
        if not name:
            return None
        by_name: list[type[ModuleClass.Module[Any]]] = []
        by_class: list[type[ModuleClass.Module[Any]]] = []
        for ih in ModuleClass.register_modules:
            cls = ih.module
            info_name = ""
            with contextlib.suppress(Exception):
                info_name = cls.info().module_name
            if info_name.lower() == name:
                by_name.append(cls)
            elif cls.__name__.lower() == name:
                by_class.append(cls)
        return (by_name or by_class or [None])[0]

    async def list_modules(self) -> str:
        """模块目录:名称 + 简介 + 触发方式(helps 截断)。"""
        lines: list[str] = []
        seen: set[str] = set()
        for ih in ModuleClass.register_modules:
            cls = ih.module
            try:
                info = cls.info()
                name, desc, helps = info.module_name, info.desc, info.helps
            except Exception:
                name, desc, helps = getattr(cls, "__name__", ""), "", ""
            key = str(name)
            if not key or key in seen:
                continue  # 类名可能都是 Module,必须按 module_name 去重
            seen.add(key)
            lines.append(f"- {name}: {desc or '(无简介)'}")
            if helps:
                lines.append(f"  触发: {helps[:200]}")
        return "可调用模块:\n" + "\n".join(lines) if lines else "(无可用模块)"

    async def run_module(self, ctx: ToolContext, module: str, command: str) -> str:
        """以合成事件驱动模块 handle();发送被捕获为段 JSON 返回;无输出时引导修正。"""
        deny = config.others.get("agent_module_deny") or []
        if module.strip().lower() in {str(d).lower() for d in deny}:
            return f"模块「{module}」已被禁用"
        cls = self._find_module(module)
        if cls is None:
            return f"模块「{module}」不存在。\n{await self.list_modules()}"
        if cls.__name__ in deny:
            return f"模块「{cls.__name__}」已被禁用"
        # 官方构建器构造 OneBot 事件 JSON → em.new 得到类型安全事件
        now = int(time.time())
        builder = OneBotEventBuilder().init(
            time=now,
            self_id=ctx.self_id or 0,
            user_id=ctx.principal_id or 0,
            group_id=cast(int, ctx.scene_id if ctx.ev_type == "group" else None),
        )
        msg_json = OneBotJsonMessageBuilder().text(command).build()
        if ctx.ev_type == "group":
            builder.as_group_message(message=msg_json, message_id="0")
            builder.group_sender(
                nickname="Agent", sex="unknown", age=0, card="", area="", level="", role="member", title=""
            )
        else:
            builder.as_private_message(message=msg_json, message_id="0")
            builder.private_sender(nickname="Agent", sex="unknown", age=0)
        event = em.new(builder.build())
        cap = _CaptureActions(self.bot_api)
        try:
            await cast(Any, cls)(cap, event).handle()
        except Exception as e:
            logger.warning(traceback.format_exc())
            out = json.dumps(cap.captured, ensure_ascii=False) if cap.captured else ""
            return f"模块「{module}」执行出错: {repr(e)}\n" + (f"已捕获输出: {out}" if out else "")
        if cap.captured:
            body = "\n".join(json.dumps(c, ensure_ascii=False) for c in cap.captured)
            return f"已调用模块「{module}」执行: {command}\n模块输出:\n{body}"
        helps = ""
        with contextlib.suppress(Exception):
            helps = cls.info().helps[:200]
        return (
            f"模块「{module}」执行完毕但无输出,可能触发方式/命令格式不对。\n"
            f"帮助: {helps or '(无帮助文本)'}\n"
            f"可调用 get_module_source 查看源码了解触发逻辑。"
        )

    async def get_module_source(self, module: str) -> str:
        """返回模块类源码(截断 4000 字),供模型理解触发方式。"""
        cls = self._find_module(module)
        if cls is None:
            return f"模块「{module}」不存在。\n{await self.list_modules()}"
        try:
            src = inspect.getsource(cls)
        except (OSError, TypeError):
            return f"无法获取模块「{module}」源码"
        body = src if len(src) <= 4000 else src[:4000] + "\n...(源码过长已截断)"
        return f"模块「{module}」源码:\n{body}"

    async def resolve_forward(self, forward_id: str) -> str:
        """解析合并转发消息:每条 node 的昵称 + 内容段 JSON(参考 TestMarkDown 的 forward_solve)。"""
        try:
            ret = await self.bot_api.get_forward_msg(forward_id)
        except Exception as e:
            return f"解析转发失败: {repr(e)}"
        nodes: Any = ret.data if hasattr(ret, "data") else ret
        lines: list[str] = []
        for node in nodes:
            if not isinstance(node, segments.Node):
                continue
            content: Any = node.content
            segs: list[Any] = []
            try:
                if content is not None:
                    segs = cast(Any, content).get_sync()
            except Exception:
                segs = [{"type": "text", "data": {"text": str(content)}}]
            lines.append(f"{node.nickname}({node.user_id}): {json.dumps(segs, ensure_ascii=False)}")
        if not lines:
            return "转发消息为空或无法解析"
        return f"转发消息 ({len(lines)} 条):\n" + "\n".join(f"{i + 1}. {line}" for i, line in enumerate(lines))

    # -- SubAgent 管理(仅主 Agent core 可用;SubAgent 调用返回错误) --

    async def sub_create(
            self, name: str, prompt: str, scene_id: int, scene_type: str, perm_group: str = "member"
    ) -> str:
        if self.sub_manager is None:
            return "调用不合法：SubAgent 不能创建 SubAgent"
        return await self.sub_manager.create(
            name,
            prompt,
            scene_type,
            scene_id,
            perm_group,
            self.session_key,
        )

    async def sub_destroy(self, sub_id: int) -> str:
        if self.sub_manager is None:
            return "调用不合法：SubAgent 管理不可用"
        return await self.sub_manager.destroy(sub_id)

    async def sub_list(self) -> str:
        if self.sub_manager is None:
            return "调用不合法：SubAgent 管理不可用"
        return self.sub_manager.list()

    async def sub_status(self, sub_id: int) -> str:
        if self.sub_manager is None:
            return "调用不合法：SubAgent 管理不可用"
        return self.sub_manager.status(sub_id)

    async def sub_feed(self, sub_id: int, content: str, perm_group: str = "member") -> str:
        if self.sub_manager is None:
            return "调用不合法：SubAgent 管理不可用"
        return await self.sub_manager.feed(sub_id, content, perm_group)

    async def report(self, content: str, need_response: bool = False) -> str:
        """SubAgent → 主 Agent 通讯:报告状态/结果/求助,注入主 Agent history。

        need_response=True 时暂停本 SubAgent 工作,等待主 Agent 用 sub_reply(report_id) 回复;
        每个 report 有唯一 report_id(主 Agent 在 subagent_status 事件中可见)。
        """
        if self.notify_main is None:
            return "调用不合法：仅 SubAgent 可向主 Agent 报告"
        self._report_seq += 1
        report_id = f"r{int(time.time())}_{self._report_seq}"
        self.notify_main(
            {
                "action": "report",
                "report_id": report_id,
                "source": self.name,
                "content": content,
                "need_response": need_response,
            }
        )
        if not need_response:
            return f"已向主 Agent 报告(#{report_id})"
        if self.report_waiters:
            return (
                f"已有等待主 Agent 回复的 report(#{next(iter(self.report_waiters))}),"
                "同一时间只能有一个待回复报告;请等待回复或使用 need_response=False"
            )
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[Any] = loop.create_future()
        self.report_waiters[report_id] = fut
        try:
            reply = await asyncio.wait_for(fut, timeout=REPORT_TIMEOUT)
        except TimeoutError:
            return f"主 Agent 未在 {REPORT_TIMEOUT}s 内回复(#{report_id})"
        finally:
            self.report_waiters.pop(report_id, None)
        return f"主 Agent 回复(#{report_id}): {reply}"

    async def sub_reply(self, report_id: str, content: str) -> str:
        """主 Agent 回复 SubAgent 的 report:向等待中的 SubAgent 投递回复内容。"""
        if self.sub_manager is None:
            return "调用不合法：SubAgent 管理不可用"
        for sub in self.sub_manager.subagents.values():
            fut = sub.core.report_waiters.get(report_id)
            if fut is not None and not fut.done():
                fut.set_result(content)
                return f"已回复 SubAgent「{sub.name}」的 report #{report_id}"
        return f"未找到待回复的 report #{report_id}(可能已超时或不存在)"

    # -- 通知注入(即时通道) --

    def inject_notice(self, ev: AgentEvent) -> None:
        """把一条事件(如 SubAgent 状态变化)即时写入 history。

        工具循环进行中(末尾是 assistant(tool_calls),或当前 action 批次的
        function_call 还没全部补上 tool output)时暂挂起:直接插入 user 会破坏
        function_call ↔ function_call_output 配对导致 API 400;由 _event_handler
        在配对完成后 flush。
        """
        msg = {
            "role": "user",
            "content": json.dumps({"event": ev.to_dict(), "system_message": "SubAgent 状态通知"}, ensure_ascii=False),
        }
        if self.working or self._tool_loop_active or (self.history and self.history[-1].get("tool_calls")):
            # 请求处理中不能插入 user:下一轮请求可能正在构造 history,统一延后。
            self.pending_notices.append(ev)
        else:
            self.history.append(msg)
        self._notice_count += 1
        if not self._wakeup_pending:
            self._wakeup_pending = True
            asyncio.create_task(self._wakeup())

    async def _wakeup(self) -> None:
        """通知触发的自主处理:基于现有 history(通知已在其中)请求 LLM,不追加新事件。"""
        seen = self._notice_count
        try:
            scene_type: Literal["group", "private", "system"] = "system"
            scene_id = 0
            if self.session_key is not None:
                scene_type = self.session_key.scene_type
                scene_id = self.session_key.scene_id
            await self.event_handler(
                event=None,
                ev_type=scene_type,
                scene_id=scene_id,
                perm_group="bot_owner" if self.role == "system" else "member",
                principal_id=None,
            )
        except Exception:
            logger.error(traceback.format_exc())
        finally:
            self._wakeup_pending = False
            if self._notice_count > seen:
                self._wakeup_pending = True
                asyncio.create_task(self._wakeup())

    def _flush_notices(self) -> None:
        """把暂挂的通知写入 history(配对完成后调用,如工具循环间隙或处理开始前)。"""
        if not self.pending_notices:
            return
        for ev in self.pending_notices:
            data = {"event": ev.to_dict(), "system_message": "SubAgent 状态通知"}
            self.history.append({"role": "user", "content": json.dumps(data, ensure_ascii=False)})
        self.pending_notices.clear()

    # -- 历史与持久化 --

    def _is_google_endpoint(self) -> bool:
        """检测 self._oai.base_url 是否指向 Google OpenAI 兼容端点。"""
        cached = getattr(self, "_google_endpoint_cache", None)
        if cached is not None:
            return cached

        result = False
        try:
            raw = getattr(self._oai, "base_url", None)
            if raw:
                url = str(raw)
                host = (urlparse(url).hostname or url).lower()
                result = any(m in host for m in _GOOGLE_HOST_MARKERS)

                if not result:
                    model = str(getattr(self, "model", None)
                                or getattr(self, "_model", "")).lower()
                    result = model.startswith("gemini") or "gemini-" in model
        except Exception:
            result = False

        self._google_endpoint_cache = result
        if result:
            logger.info("检测到 Google 兼容端点,已启用 thought_signature 自动注入")
        return result

    @staticmethod
    def _to_plain_dict(obj) -> dict:
        """将 Pydantic 模型（ChatCompletionMessage / ToolCall）安全转换为 dict，
        并完整保留 model_extra 中的 extra_content（真签名所在地）。"""
        if isinstance(obj, dict):
            return obj
        if hasattr(obj, "model_dump"):
            data = obj.model_dump(exclude_none=True)
            # 抢救 Pydantic v2 存放在 model_extra 中的 extra_content
            extra = getattr(obj, "model_extra", None) or {}
            if "extra_content" in extra and "extra_content" not in data:
                data["extra_content"] = extra["extra_content"]
            return data
        return dict(obj)

    def _patch_google_signatures(self) -> int:
        """遍历 self.history，把所有 assistant tool_calls 转为 dict 并注入 thought_signature。
        返回本次补齐签名的 tool_call 数量。"""
        if not self._is_google_endpoint():
            return 0

        patched_count = 0
        for idx, msg in enumerate(self.history):
            # 1. 若 message 本身是 Pydantic 对象，原地转为 dict
            if not isinstance(msg, dict):
                try:
                    msg = self._to_plain_dict(msg)
                    self.history[idx] = msg
                except Exception:
                    continue

            if msg.get("role") != "assistant":
                continue

            raw_calls = msg.get("tool_calls") or []
            if not isinstance(raw_calls, list) or not raw_calls:
                continue

            new_calls = []
            first_sig = None

            for call in raw_calls:
                # 2. 关键：将 ChatCompletionMessageToolCall 对象转为普通 dict
                call_dict = self._to_plain_dict(call)

                extra = call_dict.get("extra_content")
                if not isinstance(extra, dict):
                    extra = {}
                    call_dict["extra_content"] = extra

                google = extra.get("google")
                if not isinstance(google, dict):
                    google = {}
                    extra["google"] = google

                # 3. 已有真签名则保留；否则写入官方跳过校验签名
                if not google.get("thought_signature"):
                    google["thought_signature"] = GEMINI_DUMMY_SIGNATURE
                    patched_count += 1

                if not first_sig:
                    first_sig = google["thought_signature"]

                new_calls.append(call_dict)

            # 原地写回转换后的 dict 列表
            msg["tool_calls"] = new_calls

            # 4. 双保险：同时在 assistant message 顶层挂载 extra_content
            if first_sig:
                msg_extra = msg.get("extra_content")
                if not isinstance(msg_extra, dict):
                    msg_extra = {}
                    msg["extra_content"] = msg_extra
                msg_google = msg_extra.get("google")
                if not isinstance(msg_google, dict):
                    msg_google = {}
                    msg_extra["google"] = msg_google
                if not msg_google.get("thought_signature"):
                    msg_google["thought_signature"] = first_sig

        if patched_count > 0:
            logger.info(f"已为 {patched_count} 个历史 tool_call 补齐 thought_signature")
        return patched_count

    async def _history_fix(self) -> None:
        """修复悬空的 tool_calls 历史，并自动为 Google 端点补齐 thought_signature。"""
        logger.warning("尝试修复历史记录")

        # 第一步：先把所有 Pydantic 对象规范化为 dict 并补齐 Google 签名
        self._patch_google_signatures()

        pending_ids: set[str] = set()
        pending_indexes: dict[str, int] = {}
        first_invalid = len(self.history)

        for i, message in enumerate(self.history):
            if not isinstance(message, dict):
                first_invalid = min(first_invalid, i)
                continue
            if message.get("role") == "assistant":
                calls = message.get("tool_calls") or []
                if isinstance(calls, list):
                    for call in calls:
                        if isinstance(call, dict) and call.get("id"):
                            call_id = str(call["id"])
                            pending_ids.add(call_id)
                            pending_indexes[call_id] = i
            elif message.get("role") == "tool":
                call_id = str(message.get("tool_call_id") or "")
                if not call_id or call_id not in pending_ids:
                    call_start = pending_indexes.get(call_id)
                    if call_start is None:
                        call_start = next(
                            (
                                j
                                for j in range(i - 1, -1, -1)
                                if isinstance(self.history[j], dict)
                                and self.history[j].get("role") == "assistant"
                                and self.history[j].get("tool_calls")
                            ),
                            i,
                        )
                    first_invalid = min(first_invalid, call_start)
                else:
                    pending_ids.discard(call_id)
                    pending_indexes.pop(call_id, None)

        if first_invalid < len(self.history):
            del self.history[first_invalid:]
            return
        if pending_ids:
            first_pending = min(pending_indexes.values())
            del self.history[first_pending:]

    async def save(self) -> None:
        os.makedirs("./temps", exist_ok=True)
        snapshot = copy.deepcopy(self.history)

        def _dump(path: str, obj: Any) -> None:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(obj, f, indent=2, ensure_ascii=False)

        await asyncio.to_thread(_dump, self.history_path, snapshot)
        await asyncio.to_thread(_dump, self.tasks_path, self.chat_tasks)

    # -- 工具状态刷新(禁用/启用后,主/子核心的 schema 与 system prompt 保持一致) --

    def _build_system_prompt_for_role(self) -> str:
        """按角色重建 Main、SubAgent 或 System Context 提示词。"""
        if self.role == "main":
            base = _build_system_prompt()
            if self.session_key is not None:
                base += f"\n\n# 当前上下文\n\n- 当前上下文标识：`{self.session_key.value}`。"
            return base
        if self.role == "system":
            return SYSTEM_CONTEXT_PROMPT.replace("{output}", OUTPUT_RULE).replace(
                "{tools}", _build_tools_section(role="system")
            )
        base = self._base_prompt or ""
        tools = _build_tools_section(role="sub")
        if "{tools}" in base:
            return base.replace("{output}", OUTPUT_RULE).replace("{tools}", tools)
        return base + "\n\n# 可用工具\n\n" + tools + "\n\n" + OUTPUT_RULE + "\n\n" + SUBAGENT_RULE + _web_search_note()

    def _refresh_tools(self) -> None:
        """重建 tools schema 与 system prompt,并写回 history 的第一条 system。"""
        self.tools = ToolRegistry.schema(role=self.role)
        self.system_prompt = self._build_system_prompt_for_role()
        new_content = self.system_prompt.replace("[ulist]", str(config.owner))
        for i, m in enumerate(self.history):
            if isinstance(m, dict) and m.get("role") == "system":
                self.history[i]["content"] = new_content
                break
        else:
            self.history.insert(0, {"role": "system", "content": new_content})

    # -- 事件处理 --

    async def _acquire_processing_slot(self) -> None:
        """等待并原子取得全局 history 处理权;锁只保护状态切换。"""
        while True:
            await self._idle_event.wait()
            async with self._state_lock:
                if not self.working:
                    self.working = True
                    self._idle_event.clear()
                    return

    async def _release_processing_slot(self) -> None:
        async with self._state_lock:
            self.working = False
            self._idle_event.set()

    async def aclose(self) -> None:
        """释放底层 HTTP 连接池;调用方需保证没有正在进行的处理。"""
        await self._oai.close()

    async def _wait_until_idle(self) -> None:
        """等待当前全局 history 请求结束;不持锁等待。"""
        while True:
            await self._idle_event.wait()
            async with self._state_lock:
                if not self.working:
                    return

    async def event_handler(
            self,
            event: Any,
            ev_type: Literal["group", "private", "system", "nonmsg"],
            scene_id: int,
            perm_group: str = "member",
            principal_id: int | None = None,
            self_id: int | None = None,
            tool_choice: str = "auto",
    ) -> None:
        await self._acquire_processing_slot()
        try:
            await self._event_handler_with_slot(
                event=event,
                ev_type=ev_type,
                scene_id=scene_id,
                perm_group=perm_group,
                principal_id=principal_id,
                self_id=self_id,
                tool_choice=tool_choice,
            )
        finally:
            await self._release_processing_slot()

    async def _event_handler_with_slot(
            self,
            event: Any,
            ev_type: Literal["group", "private", "system", "nonmsg"],
            scene_id: int,
            perm_group: str = "member",
            principal_id: int | None = None,
            self_id: int | None = None,
            tool_choice: str = "auto",
    ) -> None:
        sem = _acquire_semaphore()
        if sem is not None:
            await sem.acquire()
        self._flush_notices()
        sys_msg = "如果要回复消息，唯一正确方法是调用工具"
        start_time = time.time()
        timer_ev = asyncio.Event()
        timer_task = asyncio.create_task(timer(600, timer_ev))
        bad_retries = 0
        task: asyncio.Task[Any] | None = None
        if event is None:
            ev_data: str | None = None
            query_text = ""
        else:
            if isinstance(event, str):
                logger.info(event)
                query_text = event
            else:
                query_text = str(event.data)
            ev = AgentEvent(
                type="message_batch",
                scene_type=ev_type,
                scene_id=scene_id,
                payload=event if isinstance(event, str) else event.data,
                source=self.name,
            )
            ev_data = json.dumps(
                {"event": ev.to_dict(), "system_message": sys_msg},
                ensure_ascii=False,
            )
        # RAG 自动注入:用本次事件文本检索相关记忆,附加到本次请求的 system 消息
        self._injected_memory = ""
        if query_text.strip():
            try:
                self._injected_memory = await asyncio.to_thread(self.mem_retrieve, query_text, 3)
            except Exception:
                self._injected_memory = ""
        try:
            while not timer_ev.is_set():
                try:
                    ctx = ToolContext(
                        actions=self.bot_api,
                        ev_type=ev_type,
                        scene_id=scene_id,
                        perm_group=perm_group,
                        principal_id=principal_id,
                        self_id=self_id,
                        runtime=self,
                        role=self.role,
                    )
                    task = asyncio.create_task(
                        self._event_handler(
                            data=ev_data,
                            ev_type=ev_type,
                            scene_id=scene_id,
                            ctx=ctx,
                            tool_choice=tool_choice,
                        )
                    )
                    while not task.done():
                        if timer_ev.is_set():
                            task.cancel("请求超时")
                            break
                        await asyncio.sleep(0.01)
                    # 取回 task 异常:否则异常成为「never retrieved」,外层重试机制(历史修复)不会触发
                    if not task.cancelled():
                        exc = task.exception()
                        if exc is not None:
                            raise exc
                    break
                except openai.BadRequestError:
                    bad_retries += 1
                    if bad_retries >= 3:
                        # 连续 3 次请求被拒(如提示词缺 json 字样等固定问题),放弃本次处理,避免死循环
                        logger.error("连续 3 次 BadRequestError，放弃本次处理")
                        break
                    logger.warning(traceback.format_exc())
                    await self._history_fix()
                except (NotImplementedError, RuntimeError) as e:
                    sys_msg = repr(e)
                    logger.warning(repr(e) + ", 正在重试")
                except Exception as e:
                    logger.error(str(e))
                    logger.error(traceback.format_exc())
        finally:
            timer_task.cancel()
            if task is not None and not task.done():
                task.cancel("外层处理结束")
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            duration = time.time() - start_time
            logger.info(f"处理完成，用时 {duration:.3f}s")
            try:
                # 事件处理已结束:此时注入待通知的 SubAgent 状态事件,不会打断 tool_calls 配对
                self._flush_notices()
                await self._finish_pending_summary()
            finally:
                if sem is not None:
                    sem.release()
            # 锁已释放,再调度自动总结;任务内部自行抢锁,与后续事件处理串行。
            self._maybe_schedule_auto_summary()

    async def _event_handler(
            self,
            data: str | None,
            ev_type: Literal["group", "private", "system", "nonmsg"],
            scene_id: int,
            ctx: ToolContext,
            tool_choice: str = "auto",
    ) -> None:
        try:
            self._refresh_tools()
            tool_choice_n: Any = self._make_tool_choice(tool_choice)
            if data is not None:
                dup = any(m.get("role") == "user" and m.get("content") == data for m in self.history)
                if not dup:
                    self.history.append({"role": "user", "content": data})
            retried = 0
            delay = 5
            while True:
                resp = await self._llm_create(tool_choice_n)
                actions, assistant_msg = self._parse_output(resp)
                logger.info(self._format_assistant_msg(assistant_msg))
                self.history.append(assistant_msg)
                if not actions:
                    break
                had_action = False
                self._tool_loop_active = True
                try:
                    for act in actions:
                        if act["kind"] == "web_search":
                            items = act.get("data") or []
                            details = (
                                " | ".join(
                                    f"{item.get('type')}#{item.get('id')} "
                                    f"action={AgentCore._short_json(item.get('action'))}"
                                    for item in items
                                    if isinstance(item, dict)
                                )
                                if isinstance(items, list)
                                else AgentCore._short_json(items)
                            )
                            logger.info(f"WebSearch: {details or '(无详情)'}")
                            had_action = True
                            continue
                        name = cast(str, act["name"])
                        call_id = cast(str, act["call_id"])
                        try:
                            params = json.loads(cast(str, act["arguments"]))
                        except json.JSONDecodeError as e:
                            logger.error("错误的JSON，重试: " + repr(e))
                            await self._history_fix()
                            await self._event_handler(
                                data=data, ev_type=ev_type, scene_id=scene_id, ctx=ctx, tool_choice=tool_choice
                            )
                            return
                        try:
                            rs = await ToolRegistry.dispatch(name, params, ctx)
                        except Exception as e:
                            rs = repr(e)
                        logger.info(
                            f"已完成工具调用： {name}({', '.join([x + '=' + str(params[x]) for x in params])}) -> {rs}"
                        )
                        self.history.append({"role": "tool", "tool_call_id": call_id, "name": name, "content": str(rs)})
                        had_action = True
                except Exception as e:
                    if isinstance(e, asyncio.CancelledError):
                        raise
                    if retried >= 5:
                        logger.error(f"{e}, 重试次数过多，放弃")
                        match ev_type:
                            case "group":
                                await ctx.actions.send_group_msg(f"Agent Mod 不能解决的异常：{e}", scene_id)
                            case "private":
                                await ctx.actions.send_private_msg(f"Agent Mod 不能解决的异常：{e}", scene_id)
                    logger.error(f"{e}, {delay}s 后重试")
                    await asyncio.sleep(delay)
                    retried += 1
                    delay += 2
                finally:
                    # 当前 assistant 的所有 function_call 都补完 tool 输出后:
                    # 1) 应用延后的人设切换(切换前自动总结);
                    # 2) 再 flush 通知;中途插入 user 会破坏 function_call↔output 配对。
                    await self._finish_pending_profile_switch()
                    await self._finish_pending_summary()
                    self._flush_notices()
                    self._tool_loop_active = False
                if ctx.release_requested:
                    logger.info(f"{self.name} 已释放本轮,长程任务交由后台处理")
                    break
                if not had_action:
                    break
            await self.save()
        except asyncio.CancelledError as e:
            logger.error(f"处理中断：{repr(e)}")
            await self._history_fix()

    # -- LLM 通道抽象(chat completions / responses api) --

    def _make_tool_choice(self, tool_choice: str) -> Any:
        if tool_choice == "auto":
            return "auto"
        if self.api_mode == "responses":
            return {"type": "function", "name": tool_choice}
        return {"type": "function", "function": {"name": tool_choice}}

    async def _download_image_data_uri(self, url: str) -> str | None:
        """下载远程图片并转成 data URI;基于 sha256(url) 的磁盘文件缓存,不驻留内存。"""
        from modules.AgentRuntime.image_cache import load_or_download

        return await load_or_download(url)

    async def _image_url_from_seg(self, seg: dict[str, Any]) -> str | None:
        """OneBot 图片段 → OpenAI image_url 可接受的 data URI。

        QQ 等渠道的图片 URL 对第三方模型通常不可直接下载,统一由 bot 本地下载后
        以 data URI 交给模型;base64/本地文件直接转换。
        """
        raw_data = seg.get("data")
        if not isinstance(raw_data, dict):
            return None
        data = raw_data
        url = str(data.get("url") or "")
        if url.startswith(("http://", "https://")):
            return await self._download_image_data_uri(url)

        file = str(data.get("file") or "")
        if file.startswith(("http://", "https://")):
            return await self._download_image_data_uri(file)

        if file.startswith("base64://"):
            raw = file[len("base64://"):]
            try:
                import filetype

                decoded = base64.b64decode(raw)
                guessed = filetype.guess(decoded)
                mime = guessed.mime if guessed is not None else "image/png"
            except Exception:
                mime = "image/png"
            return f"data:{mime};base64,{raw}"

        path = file[7:] if file.startswith("file://") else file
        if path and os.path.isfile(path):
            try:
                import filetype

                with open(path, "rb") as f:
                    raw_bytes = f.read()
                raw = base64.b64encode(raw_bytes).decode("ascii")
                guessed = filetype.guess(raw_bytes)
                mime = guessed.mime if guessed else "image/png"
                return f"data:{mime};base64,{raw}"
            except OSError:
                return None
        return None

    async def _chat_user_content(self, content: Any) -> Any:
        """用户历史消息 → Chat Completions content。

        开启 native_multimodal 且当前用户消息包含图片段时,输出 OpenAI 原生
        text/image_url 内容数组;否则保持原字符串,兼容旧行为。
        """
        if not self.native_multimodal or not isinstance(content, str):
            return content
        try:
            wrapper = json.loads(content)
        except json.JSONDecodeError:
            return content
        if not isinstance(wrapper, dict):
            return content
        event = wrapper.get("event")
        if not isinstance(event, dict):
            return content
        payload = event.get("payload")
        if isinstance(payload, str):
            try:
                batch = json.loads(payload)
            except json.JSONDecodeError:
                return content
        else:
            batch = payload
        if not isinstance(batch, list):
            return content

        parts: list[dict[str, Any]] = []
        image_count = 0
        has_text = False
        for ev in batch:
            if not isinstance(ev, dict):
                continue
            uid = str(ev.get("user_id") or "")
            message = ev.get("message")
            if not isinstance(message, list):
                continue
            texts: list[str] = []
            image_urls: list[str] = []
            for seg in message:
                if not isinstance(seg, dict):
                    continue
                seg_type = seg.get("type")
                if seg_type == "text":
                    text = str((seg.get("data") or {}).get("text", "") or "")
                    if text.strip():
                        texts.append(text)
                elif seg_type == "image" and image_count < 4:
                    image_url = await self._image_url_from_seg(seg)
                    if image_url:
                        image_urls.append(image_url)
                        image_count += 1
                    else:
                        texts.append("[图片下载失败]")
                elif seg_type not in ("image",):
                    texts.append(f"[{seg_type}]")

            text = " ".join(texts).strip()
            if text:
                parts.append({"type": "text", "text": f"{uid}: {text}" if uid else text})
                has_text = True
            for image_url in image_urls:
                parts.append({"type": "image_url", "image_url": {"url": image_url}})

        if image_count == 0:
            return content
        if not has_text:
            parts.insert(0, {"type": "text", "text": "用户发送了图片"})
        return parts

    async def _history_to_chat_messages(self) -> list[dict[str, Any]]:
        """把内部 history 转成 Chat Completions 可接受的消息列表。

        内部 history 会携带 reasoning / web_search_call / order 等 Responses 专用字段,
        直接发给 Chat Completions 会被某些供应商拒绝(如 reasoning 必须是 string)。
        这里只保留 OpenAI Chat 协议字段。
        """
        out: list[dict[str, Any]] = []
        for m in self.history:
            if not isinstance(m, dict):
                continue
            role = m.get("role")
            if role == "assistant":
                item: dict[str, Any] = {"role": "assistant", "content": m.get("content")}
                reasoning_content = m.get("reasoning_content")
                if isinstance(reasoning_content, str) and reasoning_content.strip():
                    # Chat Completions 提供方(如 rinko)接受 reasoning_content 字符串回传;
                    # 保留思考链,只丢弃 Responses 专用结构。
                    item["reasoning_content"] = reasoning_content
                tool_calls = m.get("tool_calls")
                if isinstance(tool_calls, list) and tool_calls:
                    item["tool_calls"] = [
                        {
                            "id": call.get("id", ""),
                            "type": "function",
                            "function": {
                                "name": (call.get("function") or {}).get("name", ""),
                                "arguments": (call.get("function") or {}).get("arguments", ""),
                            },
                        }
                        for call in tool_calls
                        if isinstance(call, dict)
                    ]
                out.append(item)
            elif role == "tool":
                out.append(
                    {
                        "role": "tool",
                        "tool_call_id": m.get("tool_call_id", ""),
                        "content": m.get("content", ""),
                    }
                )
            elif role == "user":
                out.append({"role": "user", "content": await self._chat_user_content(m.get("content", ""))})
            elif role == "system":
                out.append({"role": "system", "content": m.get("content", "")})
        return out

    def _with_injected_memory(self, messages: list[Any]) -> list[Any]:
        """把自动检索到的相关记忆附加到第一条 system 消息(深拷贝,不污染 history)。

        聊天历史里可能带有本地用于日志展示的 reasoning/reasoning_content;
        这些字段只作日志/排查用,发送给第三方 Chat API 前剥离,避免提供方不识别。
        """
        out = [dict(m) for m in messages]
        for m in out:
            # reasoning 列表是 Responses 内部结构,不能发给 Chat API;
            # reasoning_content 字符串在 _history_to_chat_messages 中已经按需保留。
            m.pop("reasoning", None)
            if m.get("role") == "system" and isinstance(m.get("content"), str):
                m["content"] = m["content"] + "\n\n" + self._injected_memory
                break
        return out

    async def _llm_create(self, tool_choice_n: Any) -> Any:
        print(self.history[-5:])
        if self.api_mode == "responses":
            return await self._oai.responses.create(  # pyrefly: ignore[no-matching-overload]
                model=self.model,
                input=self._with_injected_memory(self._history_to_items()),
                tools=self._tools_for_responses(),
                tool_choice=tool_choice_n,
                # 保持服务端默认的并行工具调用能力;本层会等当前 assistant 的
                # 全部 function_call 都补完 output 后才发起下一次请求。
                reasoning=cast(Any, {"effort": self.reasoning_effort}),
                text=cast(Any, {"format": {"type": "json_object"}}),
            )
        return await self._oai.chat.completions.create(
            model=self.model,
            messages=self._with_injected_memory(await self._history_to_chat_messages()),
            tools=self.tools,
            tool_choice=tool_choice_n,
            reasoning_effort=cast(Any, self.reasoning_effort),
            response_format=cast(Any, {"type": "json_object"}),
            extra_body=self.extra
        )

    def _history_to_items(self) -> list[dict[str, Any]]:
        """内部 chat 格式 history → Responses API 输入 items。

        顺序约定(关键,来自 DeepSeek 文档「输入 Items」兼容性):
        - function_call 会「归并到相邻 assistant 消息」,reasoning 明文 content 同样
          「归并到相邻 assistant 消息」:服务端按原始顺序重建 assistant 轮次,每一轮
          (web_search / function_call)都必须配有自己的 reasoning,否则报
          "The `reasoning_text` in the thinking mode must be passed back to the API."
        - web_search_call「原样回传即可,服务端自动恢复搜索结果」。
        因此必须按 _parse_output 记录的顺序(order)严格重建,不能把 reasoning 全提
        前、web_search_call 推后 —— 那会让 function_call 轮次失去配对的 reasoning。
        """
        items: list[dict[str, Any]] = []
        # tool 消息不单独输出:其内容作为对应 function_call 的 output 紧跟输出
        tool_out: dict[str, str] = {
            m.get("tool_call_id", ""): m.get("content", "") for m in self.history if m.get("role") == "tool"
        }
        for m in self.history:
            role = m.get("role")
            if role == "system":
                items.append({"type": "message", "role": "system", "content": m.get("content", "")})
            elif role == "user":
                items.append({"type": "message", "role": "user", "content": m.get("content", "")})
            elif role == "tool":
                continue  # 已在 function_call 后作为 output 输出
            elif role == "assistant":
                items.extend(self._assistant_items(m, tool_out))
        return items

    def _assistant_items(self, m: dict[str, Any], tool_out: dict[str, str]) -> list[dict[str, Any]]:
        """把一条内部 assistant 消息按原始顺序还原为 Responses items。"""
        reasoning = list(m.get("reasoning") or [])
        ws = list(m.get("web_search_call") or [])
        fcs = list(m.get("tool_calls") or [])
        order = m.get("order")
        out: list[dict[str, Any]] = []
        if order:
            ri = wi = fi = 0
            last_reasoning: dict[str, Any] | None = None
            last_was_reasoning = False

            def ensure_reasoning_for_call() -> None:
                nonlocal ri, last_reasoning, last_was_reasoning
                if last_reasoning is None and ri < len(reasoning):
                    # order 与 reasoning 列表不一致时,先把未消费的 reasoning 补到调用前。
                    last_reasoning = reasoning[ri]
                    out.append(last_reasoning)
                    ri += 1
                    last_was_reasoning = True
                    return
                if last_was_reasoning or last_reasoning is None:
                    return
                # DeepSeek 要求每个 function_call / web_search_call 都有配对的
                # reasoning_text;原生响应可能一个 reasoning 后跟多个 tool call,
                # 这里复制最近一条 reasoning 补齐,否则下一个请求 400。
                dup = copy.deepcopy(last_reasoning)
                dup["id"] = f"{last_reasoning.get('id', 'reasoning')}_dup_{uuid.uuid4().hex}"
                out.append(dup)
                last_was_reasoning = True

            for typ in order:
                if typ == "reasoning" and ri < len(reasoning):
                    last_reasoning = reasoning[ri]
                    out.append(last_reasoning)
                    ri += 1
                    last_was_reasoning = True
                elif typ == "web_search_call" and wi < len(ws):
                    ensure_reasoning_for_call()
                    out.append(ws[wi])
                    wi += 1
                    last_was_reasoning = False
                elif typ == "function_call" and fi < len(fcs):
                    ensure_reasoning_for_call()
                    fc = fcs[fi]
                    fi += 1
                    cid = fc.get("id", "")
                    out.append(
                        {
                            "type": "function_call",
                            "call_id": cid,
                            "name": fc["function"]["name"],
                            "arguments": fc["function"]["arguments"],
                        }
                    )
                    out.append({"type": "function_call_output", "call_id": cid, "output": tool_out.get(cid, "")})
                    last_was_reasoning = False
                elif typ == "message":
                    out.append({"type": "message", "role": "assistant", "content": m.get("content", "")})
                    last_was_reasoning = False
            return out

        # 旧历史兼容(无 order):reasoning 与 ws / fc 依次配对,尽力贴近真实顺序
        def _take_reasoning() -> None:
            if reasoning:
                out.append(reasoning.pop(0))

        for w in ws:
            _take_reasoning()
            out.append(w)
        for fc in fcs:
            _take_reasoning()
            cid = fc.get("id", "")
            out.append(
                {
                    "type": "function_call",
                    "call_id": cid,
                    "name": fc["function"]["name"],
                    "arguments": fc["function"]["arguments"],
                }
            )
            out.append({"type": "function_call_output", "call_id": cid, "output": tool_out.get(cid, "")})
        for r in reasoning:
            out.append(r)
        if m.get("content"):
            out.append({"type": "message", "role": "assistant", "content": m["content"]})
        return out

    @staticmethod
    def _short_json(value: Any, limit: int = 240) -> str:
        text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
        return text if len(text) <= limit else text[:limit] + "..."

    @staticmethod
    def _short_text(value: Any, limit: int = 300) -> str:
        """把任意值压成单行文本(JSON 或原文),过长截断。"""
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        text = re.sub(r"\s+", " ", text).strip()
        return text if len(text) <= limit else text[:limit] + "..."

    @staticmethod
    def _reasoning_text(item: dict[str, Any]) -> str:
        content = item.get("content")
        if isinstance(content, list):
            return " ".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
        return str(content or "")

    @staticmethod
    def _format_assistant_msg(assistant_msg: dict[str, Any]) -> str:
        """把 Completion 格式化为 YAML 风格的多行日志,便于 logger 逐行加时间前缀。"""
        lines = ["Completion:"]

        content = assistant_msg.get("content")
        lines.append(f"  - content: {AgentCore._short_text(content if content is not None else '')}")

        reasoning = assistant_msg.get("reasoning")
        if isinstance(reasoning, list) and reasoning:
            lines.append("  - reasoning:")
            for item in reasoning:
                if not isinstance(item, dict):
                    continue
                enabled = item.get("enabled")
                if not isinstance(enabled, bool):
                    enabled = item.get("status") == "completed"
                lines.append(f"      - enabled: {str(enabled).lower()}")
                lines.append(f"        content: {AgentCore._short_text(AgentCore._reasoning_text(item))}")

        tool_calls = assistant_msg.get("tool_calls")
        if isinstance(tool_calls, list) and tool_calls:
            lines.append("  - tool_calls:")
            for call in tool_calls:
                if not isinstance(call, dict):
                    continue
                function = call.get("function")
                if not isinstance(function, dict):
                    continue
                name = str(function.get("name") or "?")
                arguments = function.get("arguments")
                if isinstance(arguments, str):
                    with contextlib.suppress(json.JSONDecodeError):
                        arguments = json.loads(arguments)
                if isinstance(arguments, dict):
                    params = ", ".join(f"{k}={AgentCore._short_json(v, 160)}" for k, v in arguments.items())
                else:
                    params = AgentCore._short_json(arguments)
                lines.append(f"      - {name}({params})")

        web_search = assistant_msg.get("web_search_call")
        if isinstance(web_search, list) and web_search:
            lines.append("  - web_search:")
            for item in web_search:
                if not isinstance(item, dict):
                    continue
                lines.append(f"      - id: {item.get('id')}")
                lines.append(f"        action: {AgentCore._short_json(item.get('action'))}")

        return "\n".join(lines)

    def _tools_for_responses(self) -> list[dict[str, Any]] | None:
        """Responses API 工具格式(与 chat 的 function 包装不同)+ 服务端 web_search。"""
        tools: list[dict[str, Any]] = []
        for t in self.tools:
            fn = t["function"]
            tools.append(
                {
                    "type": "function",
                    "name": fn["name"],
                    "description": fn["description"],
                    "parameters": fn["parameters"],
                }
            )
        if self.web_search:
            tools.append({"type": "web_search"})
        return tools or None

    def _parse_output(self, resp: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """解析 LLM 响应为 (动作列表, assistant 内部消息)。"""
        if self.api_mode == "responses":
            actions: list[dict[str, Any]] = []
            contents: list[str] = []
            tool_calls: list[dict[str, Any]] = []
            reasoning: list[dict[str, Any]] = []
            web_search: list[dict[str, Any]] = []
            order: list[str] = []  # 原始 item 顺序:回传时必须保持,DeepSeek 按此归并 assistant 轮次
            for item in resp.output:
                itype = getattr(item, "type", "")
                if itype == "message":
                    content = getattr(item, "content", "")
                    if isinstance(content, str):
                        contents.append(content)
                    else:
                        for part in content or []:
                            contents.append(getattr(part, "text", "") or "")
                    order.append("message")
                elif itype == "reasoning":
                    # 思考模式:reasoning item 必须完整回传,否则 API 400
                    reasoning.append(item.model_dump() if hasattr(item, "model_dump") else dict(item))
                    order.append("reasoning")
                elif itype == "function_call":
                    call_id = getattr(item, "call_id", "")
                    name = getattr(item, "name", "")
                    arguments = getattr(item, "arguments", "{}")
                    tool_calls.append(
                        {"id": call_id, "type": "function", "function": {"name": name, "arguments": arguments}}
                    )
                    actions.append({"kind": "function", "call_id": call_id, "name": name, "arguments": arguments})
                    order.append("function_call")
                elif itype == "web_search_call":
                    # 服务端搜索调用:必须完整回传(含 action/status),只回 id 会 400
                    web_search.append(item.model_dump() if hasattr(item, "model_dump") else dict(item))
                    order.append("web_search_call")
            raw_content = "".join(contents)
            if raw_content:
                # Flash 偶发把 DSML/XML 伪工具调用写进 content;解析为标准 function_call
                # 并清掉原文,避免污染 history 与后续请求。
                content, embedded_calls, embedded_actions = _parse_embedded_tool_calls(raw_content)
                if embedded_calls:
                    tool_calls.extend(embedded_calls)
                    actions.extend(embedded_actions)
                    # 回传顺序:message 之后补 function_call,工具执行后才有 output。
                    order.extend(["function_call"] * len(embedded_calls))
            else:
                content = raw_content
            assistant_msg: dict[str, Any] = {"role": "assistant", "content": content}
            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls
            if reasoning:
                assistant_msg["reasoning"] = reasoning
            if web_search:
                assistant_msg["web_search_call"] = web_search
                actions.append({"kind": "web_search", "data": web_search})
            if order:
                assistant_msg["order"] = order
            return actions, assistant_msg
        mess = resp.choices[0].message
        actions = [
            {
                "kind": "function",
                "call_id": tc.id,
                "name": cast(str, cast(Any, tc).function.name),
                "arguments": cast(str, cast(Any, tc).function.arguments),
            }
            for tc in (mess.tool_calls or [])
        ]
        assistant_msg: dict[str, Any] = mess.to_dict()
        raw_content = cast(str, getattr(mess, "content", "") or "")
        reasoning_content = getattr(mess, "reasoning_content", None)
        if reasoning_content:
            assistant_msg["reasoning"] = [
                {
                    "type": "reasoning",
                    "id": f"chat_reasoning_{int(time.time() * 1000)}",
                    "summary": list[str](),
                    "status": "completed",
                    "content": [{"type": "reasoning_text", "text": str(reasoning_content)}],
                }
            ]
        if raw_content:
            content, embedded_calls, embedded_actions = _parse_embedded_tool_calls(raw_content)
            assistant_msg["content"] = content
            if embedded_calls:
                assistant_msg["tool_calls"] = list(assistant_msg.get("tool_calls") or []) + embedded_calls
                actions.extend(embedded_actions)
        else:
            assistant_msg["content"] = ""
        return actions, assistant_msg
