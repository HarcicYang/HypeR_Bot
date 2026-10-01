"""OneBot ``file`` 消息段。

2.0.1 起 OneBot 适配器通过段注册表原生支持 ``file`` 段（``OneBotFile``，
覆盖 file / file_name / file_id / file_hash / url），本模块保留给需要显式
判断或解析文件段的调用方；对未注册该段类型的协议实现保留 UnknownSegment 兜底。
"""

from typing import Any

from hyperot.v2 import Segment, UnknownSegment
from hyperot_adapter_onebot.segments import OneBotFile

__all__ = ["OneBotFile", "is_file_segment", "parse_file_segment"]


def is_file_segment(segment: Segment) -> bool:
    return isinstance(segment, OneBotFile) or (isinstance(segment, UnknownSegment) and segment.wire_type == "file")


def parse_file_segment(segment: Segment) -> dict[str, Any] | None:
    """取出 file 段的 file_id / 文件名 / 大小 / hash；不是 file 段时返回 None。"""
    if isinstance(segment, OneBotFile):
        return {
            "file_id": str(segment.file_id or segment.source),
            "file_name": str(segment.name or ""),
            "size": segment.size or 0,
            "file_hash": str(getattr(segment, "file_hash", "") or ""),
        }
    if not is_file_segment(segment):
        return None
    assert isinstance(segment, UnknownSegment)
    data = segment.data
    return {
        "file_id": str(data.get("file_id") or data.get("file") or ""),
        "file_name": str(data.get("file_name") or data.get("name") or ""),
        "size": data.get("size") or data.get("file_size") or 0,
        "file_hash": str(data.get("file_hash") or ""),
    }
