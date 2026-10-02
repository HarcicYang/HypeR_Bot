"""OneBot 扩展消息段（keyboard / music / stream / longmsg）。

V2 的消息段是标准库 dataclass。要让自定义段真正过适配器收发，需要注册进
``client.adapter.segment_codec`` 的段注册表；未注册的 wire 类型会退化为
``UnknownSegment``（仍可收发，但没有类型与 ``display_text``）。

这里用一族透传段覆盖 OneBot 侧适配器没有内置类型的 wire 段：解码时原样
保留 ``data``，编码时按 ``wire`` 声明的类型名输出。inline 合并转发
（带 content 的 forward）继续用 ``UnknownSegment``——``forward`` 这个
wire 类型已被适配器内置占用，替换它会影响所有入站转发的解码。
"""

from __future__ import annotations

import dataclasses
from typing import Any, ClassVar

from hyperot.v2 import Segment
from typing_extensions import override


@dataclasses.dataclass(frozen=True)
class WireDataSegment(Segment):
    """携带原始 OneBot wire data 的透传段；子类用 wire 声明协议段类型名。"""

    data: dict[str, Any] = dataclasses.field(default_factory=dict)
    wire: ClassVar[str] = ""

    @override
    def display_text(self) -> str:
        return f"[{self.wire or type(self).__name__}]"


class KeyboardSegment(WireDataSegment):
    wire = "keyboard"


class MusicSegment(WireDataSegment):
    wire = "music"


class StreamSegment(WireDataSegment):
    wire = "stream"


class LongMessageSegment(WireDataSegment):
    wire = "longmsg"


EXTRA_SEGMENTS: tuple[type[WireDataSegment], ...] = (
    KeyboardSegment,
    MusicSegment,
    StreamSegment,
    LongMessageSegment,
)


def _decoder(segment_type: type[WireDataSegment]) -> Any:
    def decode(item: Any) -> Segment:
        data = item.get("data") if isinstance(item, dict) else None
        return segment_type(data=data if isinstance(data, dict) else {})

    return decode


def _encoder(segment: Segment) -> dict[str, Any]:
    return {"type": getattr(segment, "wire", ""), "data": getattr(segment, "data", {})}


def register_extra_segments(codec: Any) -> list[str]:
    """把扩展段注册进适配器段注册表；返回本次成功注册的 wire 类型名。"""
    registered: list[str] = []
    for segment_type in EXTRA_SEGMENTS:
        try:
            codec.register_segment(
                segment_type,
                wire_type=segment_type.wire,
                decode=_decoder(segment_type),
                encode=_encoder,
                replace=True,
            )
        except ValueError:
            continue  # 适配器不支持 replace 或注册参数不兼容时保持幂等
        registered.append(segment_type.wire)
    return registered
