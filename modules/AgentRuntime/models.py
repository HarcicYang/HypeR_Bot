"""Shared Agent runtime models and storage locations."""

import dataclasses
import time
from typing import Any, Literal, cast

HISTORY_PATH = "./temps/agent_history.json"
TASKS_PATH = "./temps/agent_tasks.json"
SESSIONS_PATH = "./temps/agent_sessions"
SYSTEM_PATH = "./temps/agent_system"
REPORT_TIMEOUT = 300


@dataclasses.dataclass(frozen=True)
class SessionKey:
    scene_type: Literal["group", "private", "system"]
    scene_id: int

    @classmethod
    def parse(cls, value: str) -> "SessionKey":
        scene_type, sep, raw_id = value.partition(":")
        if not sep or scene_type not in ("group", "private", "system"):
            raise ValueError("上下文标识必须为 group:<群号>、private:<QQ号> 或 system:0")
        try:
            scene_id = int(raw_id)
        except ValueError as e:
            raise ValueError("上下文 id 必须是整数") from e
        if scene_type == "system" and scene_id != 0:
            raise ValueError("系统上下文只能是 system:0")
        return cls(cast(Literal["group", "private", "system"], scene_type), scene_id)

    @property
    def value(self) -> str:
        return f"{self.scene_type}:{self.scene_id}"

    @property
    def directory(self) -> str:
        if self.scene_type == "system":
            return SYSTEM_PATH
        return f"{SESSIONS_PATH}/{self.scene_type}_{self.scene_id}"


@dataclasses.dataclass
class AgentEvent:
    type: str
    scene_type: str
    scene_id: int | None
    payload: Any
    source: str = "main"
    time: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "scene": {"type": self.scene_type, "id": self.scene_id},
            "payload": self.payload,
            "source": self.source,
            "time": self.time or int(time.time()),
        }


@dataclasses.dataclass
class SysRequest:
    """一条已受理、待 System Context 处理并回调的系统请求。"""

    op: str
    source: SessionKey  # 发起方会话(分组/私聊),回调消息发往此处
    principal_id: int | None  # 发起用户 QQ
    self_id: int | None
    reply_message_id: str | None  # 原命令 message_id,回调时挂回复引用
    payload: dict[str, Any]
    created_at: float = 0.0

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = time.time()
