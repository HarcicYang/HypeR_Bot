"""Project-local extension for the OneBot ``file`` message segment."""

import dataclasses

from hyperot.protocol.segments import SegmentBase

__all__ = ["File"]


@dataclasses.dataclass
class File(SegmentBase, st="file", su="[文件: <file_name>]"):
    """OneBot file segment used by NapCat and compatible implementations."""

    file_name: str = ""
    file_hash: str = ""
    file_id: str = ""
    url: str = ""
