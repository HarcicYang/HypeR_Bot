"""Buffered QQ message collection for Agent contexts."""

import asyncio
import json
import math
import time
import traceback
from typing import Any, Literal, Protocol

from hyperot import configurator, hyperogger
from hyperot.events import MessageEvent

from modules.AgentTools.info_tools import GEMINI_MODEL

config = configurator.BotConfig.get("hyper-bot")
logger = hyperogger.Logger()
logger.set_level(config.log_level)


class EventHandlerCore(Protocol):
    async def event_handler(
        self,
        event: Any,
        ev_type: Literal["group", "private", "system", "nonmsg"],
        scene_id: int,
        perm_group: str = "member",
        principal_id: int | None = None,
        self_id: int | None = None,
        tool_choice: str = "auto",
    ) -> None: ...


class Collector:
    MAX_BUFFER = 80

    def __init__(self, sid: int, stype: Literal["grp", "usr"], core: EventHandlerCore) -> None:
        self.sid = sid
        self.stype = stype
        self.core = core
        self.buffer: list[dict[str, Any]] = []
        self.delay = 8.0
        self.doing_task: asyncio.Task[Any] | None = None
        self.last_receive = 0.0
        self.active = False
        self.replying = False
        self.principal_id: int | None = None
        self.perm_group = "member"
        self.self_id: int | None = None

    @staticmethod
    def _event_text(event: dict[str, Any]) -> str:
        parts: list[str] = []
        for segment in event.get("message", []):
            if segment.get("type") == "text":
                parts.append((segment.get("data") or {}).get("text", ""))
            else:
                parts.append(f"[{segment.get('type')}]")
        return "".join(parts)

    def _timeline(self) -> str:
        lines: list[str] = []
        for event in self.buffer:
            lines.append(f"[{event.get('time')}] {event.get('user_id')}: {self._event_text(event)}")
        return "\n".join(lines)

    async def _compress(self) -> dict[str, Any]:
        raw = self._timeline()
        try:
            key = config.others.get("gemini_key")
            if key:
                from google import genai

                client = genai.Client(api_key=key)
                result = await asyncio.to_thread(
                    client.models.generate_content,
                    model=GEMINI_MODEL,
                    contents="请将以下QQ群聊天记录压缩为一段简洁的中文摘要，保留关键话题、事件、人物与待办信息，不要寒暄：\n\n"
                    + raw[:8000],
                )
                summary = (result.text or "").strip()
                if summary:
                    return {
                        "compressed": True,
                        "note": f"以下为 {len(self.buffer)} 条消息的 LLM 摘要:",
                        "summary": summary,
                    }
        except Exception:
            logger.warning(f"{self.stype} {self.sid}: LLM 摘要失败,退回时间线拼接")
        return {
            "compressed": True,
            "note": f"以下为 {len(self.buffer)} 条消息的压缩摘要(按时间顺序,发送者+时间+文本):",
            "summary": raw,
        }

    async def _maybe_compress(self) -> None:
        if len(self.buffer) >= self.MAX_BUFFER:
            self.buffer = [await self._compress()]
            logger.info(f"{self.stype} {self.sid}: 缓存达 {self.MAX_BUFFER} 条,已压缩为单条摘要")

    def _update_delay(self, last: float, length: int) -> None:
        rate = last / self.delay
        weight = 1 if length * 0.2 <= 1 else length * 0.2
        self.delay = (2 / 3) * (1 - math.cos(math.pi * rate)) + (2 / 3) * weight + 2.5
        self.delay = max(min(self.delay, 16), 5)

    async def append(self, event: MessageEvent) -> None:
        await self.append_batch([event.data])

    async def append_batch(self, events: list[dict[str, Any]]) -> None:
        if not events:
            return
        self.buffer.extend(events)
        await self._maybe_compress()
        now = time.time()
        length = len(str(events[-1].get("message", "")))
        if len(self.buffer) > len(events):
            self._update_delay(now - self.last_receive, length)
        else:
            weight = 1 if length * 0.2 <= 1 else length * 0.2
            self.delay = max(min(self.delay * weight, 16), 5)
        self.last_receive = now
        if self.active and not self.replying:
            if self.doing_task is not None and not self.doing_task.done():
                self.doing_task.cancel()
            self.doing_task = asyncio.create_task(self._sleep_loop())

    async def start(self, principal_id: int | None, perm_group: str, self_id: int | None = None) -> None:
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
            self.replying = True
            batch = list(self.buffer)
            try:
                await self.core.event_handler(
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
