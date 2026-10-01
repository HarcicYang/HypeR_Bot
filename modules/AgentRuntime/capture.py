"""Agent 驱动其它 bot 模块时的捕获门面（v2 ClientAPI 版）。

被驱动模块通过 ``ModuleClass.Module`` 拿到 ``client`` / ``client.api``；
这里包装真实 ``ClientAPI``：``scene/group/user`` 的 ``send()`` 只记录不外发，
其余调用（撤回、禁言、raw 等）原样透传给真实 API。
"""

import os
import shutil
import time
from typing import Any

from hyperot.v2 import ClientAPI, Event, Message, SceneType
from hyperot.v2.actions import SendResult
from hyperot.v2.api import SceneAPI
from hyperot_adapter_onebot.events import translate_event
from hyperot_adapter_onebot.segments import OneBotSegmentCodec
from typing_extensions import override

_codec = OneBotSegmentCodec()

# 捕获侧自带 codec 实例，与适配器上收发的那个不同；扩展段需在本实例再次
# 注册（幂等），否则捕获含扩展段的消息会编码失败。
from modules.OneBotExtraSegments import register_extra_segments  # noqa: E402

register_extra_segments(_codec)


def decode_message_event(data: dict[str, Any]) -> Event | None:
    """把 OneBot 事件 JSON 翻译为 v2 事件(适配器官方链路,供 Agent 合成事件用)。

    main.py 在 client.adapter.segment_codec 上注册扩展段,但该 codec 不经 ClientAPI 暴露,
    这里复用捕获侧已注册扩展段的同一实例,避免编码路径分叉。
    """
    return translate_event(data, _codec)


def _preserve_image_files(segs: list[Any]) -> list[Any]:
    out: list[Any] = []
    for seg in segs:
        if isinstance(seg, dict) and seg.get("type") == "image":
            data = seg.get("data") or {}
            file = str(data.get("file") or data.get("url") or "")
            if file.startswith("file://"):
                src = file[len("file://") :]
                if os.path.isfile(src):
                    try:
                        os.makedirs(CaptureActions.CAPTURE_DIR, exist_ok=True)
                        dst = os.path.join(
                            CaptureActions.CAPTURE_DIR,
                            f"{int(time.time() * 1000)}_{os.path.basename(src)}",
                        )
                        shutil.copy2(src, dst)
                        data = dict(data)
                        preserved = "file://" + os.path.abspath(dst).replace("\\", "/")
                        data["file"] = preserved
                        data["url"] = preserved
                        seg = dict(seg)
                        seg["data"] = data
                    except OSError:
                        pass
        out.append(seg)
    return out


def _segments_json(message: Any) -> list[Any]:
    if isinstance(message, Message):
        try:
            return _preserve_image_files(_codec.encode_segments(message))
        except TypeError:
            # 未注册的段类型无法编码：退化为整条文本，保证 Agent 工具不中断
            return [{"type": "text", "data": {"text": str(message)}}]
    return [{"type": "text", "data": {"text": str(message)}}]


class _RecordingScene:
    def __init__(self, inner: SceneAPI, sink: list[dict[str, Any]]) -> None:
        self._inner = inner
        self._sink = sink

    async def send(self, message: Message | str) -> SendResult:
        self._sink.append({"message": _segments_json(message)})
        return SendResult(message_id="0")

    def __getattr__(self, name: str) -> Any:
        if name == "_inner":
            raise AttributeError(name)
        return getattr(self._inner, name)


class _RecordingGroup:
    def __init__(self, inner: Any, sink: list[dict[str, Any]]) -> None:
        self._inner = inner
        self._sink = sink

    async def send(self, message: Message | str) -> SendResult:
        self._sink.append({"group_id": int(self._inner.group_id), "message": _segments_json(message)})
        return SendResult(message_id="0")

    def __getattr__(self, name: str) -> Any:
        if name == "_inner":
            raise AttributeError(name)
        return getattr(self._inner, name)


class _RecordingUser:
    def __init__(self, inner: Any, sink: list[dict[str, Any]]) -> None:
        self._inner = inner
        self._sink = sink

    async def send(self, message: Message | str) -> SendResult:
        self._sink.append({"user_id": int(self._inner.user_id), "message": _segments_json(message)})
        return SendResult(message_id="0")

    def __getattr__(self, name: str) -> Any:
        if name == "_inner":
            raise AttributeError(name)
        return getattr(self._inner, name)


class _RecordingAPI(ClientAPI):
    """拦截发送系方法的 ClientAPI 包装；其余入口透传。"""

    def __init__(self, inner: ClientAPI, sink: list[dict[str, Any]]) -> None:
        super().__init__(inner._context)
        self._inner = inner
        self._sink = sink

    @override
    def scene(self, scene_type: SceneType, scene_id: str | int) -> Any:
        return _RecordingScene(self._inner.scene(scene_type, scene_id), self._sink)

    @override
    def group(self, group_id: str | int) -> Any:
        return _RecordingGroup(self._inner.group(group_id), self._sink)

    @override
    def user(self, user_id: str | int) -> Any:
        return _RecordingUser(self._inner.user(user_id), self._sink)

    def __getattr__(self, name: str) -> Any:
        if name == "_inner":
            raise AttributeError(name)
        return getattr(self._inner, name)


class CaptureActions:
    """Agent 驱动模块时替换 client 的捕获门面：send 只记录，其余透传。"""

    CAPTURE_DIR = "./temps/agent_capture"

    def __init__(self, real: ClientAPI) -> None:
        self._real = real
        self.captured: list[dict[str, Any]] = []

    @property
    def api(self) -> _RecordingAPI:
        return _RecordingAPI(self._real, self.captured)

    def __getattr__(self, name: str) -> Any:
        if name == "_real":
            raise AttributeError(name)
        return getattr(self._real, name)
