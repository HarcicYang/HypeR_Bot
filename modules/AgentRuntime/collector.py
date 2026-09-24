"""Buffered QQ message and notice collection for Agent contexts."""

import asyncio
import json
import math
import time
import traceback
from collections.abc import Callable
from typing import Any, Literal, Protocol

from hyperot import configurator, hyperogger
from hyperot.events import Event

from modules.AgentRuntime.event_text import event_actor_id, event_text
from modules.AgentRuntime.models import EvType, PermGroup

config = configurator.BotConfig.get("hyper-bot")
logger = hyperogger.Logger()
logger.set_level(config.log_level)

# 缓冲达到 MAX_BUFFER 条时,把最旧的事件折叠成一条压缩摘要(仅用时间线拼接,不再调用 LLM)。
# 折叠后保留最近 KEEP_AFTER_COMPRESS 条原始事件,摘要文本自身受 MAX_SUMMARY_CHARS 限制。
DEFAULT_MAX_BUFFER = 80
DEFAULT_KEEP_AFTER_COMPRESS = 60
DEFAULT_MAX_SUMMARY_CHARS = 8000
TRUNCATED_MARK = "（更早的压缩内容已按字符上限淘汰）"


def _config_int(key: str, default: int) -> int:
    """读取 config.others 中的正整数配置,非法值回退默认。"""
    try:
        value = int(config.others.get(key) or default)
    except (TypeError, ValueError):
        logger.warning(f"配置 {key} 非法,使用默认值 {default}")
        return default
    return value if value > 0 else default


class EventHandlerCore(Protocol):
    async def event_handler(
        self,
        event: Any,
        ev_type: EvType,
        scene_id: int,
        perm_group: PermGroup = "member",
        principal_id: int | None = None,
        self_id: int | None = None,
        tool_choice: str = "auto",
    ) -> None: ...


class Collector:
    MAX_BUFFER = DEFAULT_MAX_BUFFER

    def __init__(
        self,
        sid: int,
        stype: Literal["grp", "usr"],
        resolve_core: Callable[[], EventHandlerCore | None],
    ) -> None:
        """resolve_core: 使用当前会话的 AgentCore(惰性解析)。

        不直接持有 core:空闲回收可能删除并重建核心,collector 只保留
        缓冲区与收集窗口,发起处理时经回调现取(为空会保留 buffer 重试)。
        """
        self.sid = sid
        self.stype = stype
        self._resolve_core = resolve_core
        self.max_buffer = _config_int("agent_collector_max_buffer", DEFAULT_MAX_BUFFER)
        self.keep_after_compress = _config_int(
            "agent_collector_keep_after_compress", DEFAULT_KEEP_AFTER_COMPRESS
        )
        self.max_summary_chars = _config_int("agent_collector_max_summary_chars", DEFAULT_MAX_SUMMARY_CHARS)
        if self.keep_after_compress >= self.max_buffer:
            # 保留量不小于触发线会让折叠永不发生(缓冲将无上限增长),直接回退整套默认值。
            logger.warning(
                f"agent_collector_keep_after_compress({self.keep_after_compress}) 不小于 "
                f"agent_collector_max_buffer({self.max_buffer}),回退为默认 "
                f"{DEFAULT_MAX_BUFFER}/{DEFAULT_KEEP_AFTER_COMPRESS}"
            )
            self.max_buffer = DEFAULT_MAX_BUFFER
            self.keep_after_compress = DEFAULT_KEEP_AFTER_COMPRESS
        self.buffer: list[dict[str, Any]] = []
        self.delay = 8.0
        self.doing_task: asyncio.Task[Any] | None = None
        self.last_receive = 0.0
        self.active = False
        self.replying = False
        self.principal_id: int | None = None
        self.perm_group: PermGroup = "member"
        self.self_id: int | None = None

    def _timeline(self, events: list[dict[str, Any]]) -> str:
        """把事件渲染为时间线文本;已折叠的摘要条目直接取其摘要正文。"""
        lines: list[str] = []
        for event in events:
            if event.get("compressed"):
                summary = event.get("summary")
                if isinstance(summary, str) and summary.strip():
                    lines.append(summary.strip())
                continue
            lines.append(f"[{event.get('time')}] {event_actor_id(event)}: {event_text(event)}")
        return "\n".join(lines)

    def _compress(self) -> None:
        """把最旧的事件折叠进缓冲头部的一条压缩摘要。

        字符上限只约束压缩摘要本身(超限时从最旧处截断),原始事件不做截断。
        """
        overflow = len(self.buffer) - self.keep_after_compress
        if overflow <= 0:
            return
        folded = self.buffer[:overflow]
        self.buffer = self.buffer[overflow:]
        text = self._timeline(folded)
        old_digest = next((item for item in folded if item.get("compressed")), None)
        count = (int(old_digest.get("count") or 0) if old_digest else 0) + sum(
            1 for item in folded if not item.get("compressed")
        )
        if len(text) > self.max_summary_chars:
            tail = text[-(self.max_summary_chars - len(TRUNCATED_MARK) - 1) :]
            newline = tail.find("\n")
            if 0 <= newline < 200:
                tail = tail[newline + 1 :]
            text = f"{TRUNCATED_MARK}\n{tail}"
        self.buffer.insert(
            0,
            {
                "compressed": True,
                "count": count,
                "note": f"以下为较早 {count} 条消息的压缩摘要(按时间顺序,发送者+时间+文本):",
                "summary": text,
            },
        )

    def _maybe_compress(self) -> None:
        if len(self.buffer) < self.max_buffer:
            return
        before = len(self.buffer)
        self._compress()
        logger.info(
            f"{self.stype} {self.sid}: 缓存达 {before} 条,"
            f"已把最早的 {before - len(self.buffer)} 条折叠为压缩摘要"
        )

    def _update_delay(self, last: float, length: int) -> None:
        rate = last / self.delay
        weight = 1 if length * 0.2 <= 1 else length * 0.2
        self.delay = (2 / 3) * (1 - math.cos(math.pi * rate)) + (2 / 3) * weight + 2.5
        self.delay = max(min(self.delay, 16), 5)

    async def append(self, event: Event) -> None:
        await self.append_batch([event.data])

    async def append_passive(self, event_data: dict[str, Any]) -> None:
        """只把事件放进 buffer,不更新节奏、不重置收集窗口(供通知与非白名单消息使用)。"""
        self.buffer.append(event_data)
        self._maybe_compress()

    async def append_batch(self, events: list[dict[str, Any]]) -> None:
        if not events:
            return
        had_pending = bool(self.buffer)
        self.buffer.extend(events)
        self._maybe_compress()
        now = time.time()
        length = len(event_text(events[-1]))
        if had_pending:
            self._update_delay(now - self.last_receive, length)
        else:
            weight = 1 if length * 0.2 <= 1 else length * 0.2
            self.delay = max(min(self.delay * weight, 16), 5)
        self.last_receive = now
        if self.active and not self.replying:
            if self.doing_task is not None and not self.doing_task.done():
                self.doing_task.cancel()
            self.doing_task = asyncio.create_task(self._sleep_loop())

    async def start(self, principal_id: int | None, perm_group: PermGroup, self_id: int | None = None) -> None:
        if self.active or self.replying:
            return
        self.active = True
        self.principal_id = principal_id
        self.perm_group = perm_group
        self.self_id = self_id
        if self.doing_task is not None and not self.doing_task.done():
            self.doing_task.cancel()
        self.doing_task = asyncio.create_task(self._sleep_loop())

    async def _sleep_loop(self) -> None:
        try:
            await asyncio.sleep(self.delay)
            core = self._resolve_core()
            if core is None:
                # 核心暂不可用(管理器未就绪/被回收后尚不可建):保留 buffer,结束本窗口,
                # 由后续消息重新拉起,不丢弃已缓存内容。
                if self.buffer:
                    self.active = True
                    self.doing_task = asyncio.create_task(self._sleep_loop())
                else:
                    self.active = False
                return
            self.replying = True
            batch = list(self.buffer)
            try:
                await core.event_handler(
                    event=json.dumps(batch, ensure_ascii=False),
                    ev_type="group" if self.stype == "grp" else "private",
                    scene_id=self.sid,
                    perm_group=self.perm_group,
                    principal_id=self.principal_id,
                    self_id=self.self_id,
                )
            except Exception:
                logger.error(traceback.format_exc())
            finally:
                self.replying = False
                batch_ids = {id(item) for item in batch}
                self.buffer = [item for item in self.buffer if id(item) not in batch_ids]
                if self.buffer:
                    self.active = True
                    self.doing_task = asyncio.create_task(self._sleep_loop())
                else:
                    self.active = False
        except asyncio.CancelledError:
            pass
