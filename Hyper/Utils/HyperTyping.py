from typing import Optional, TypeVar, TypedDict


T = TypeVar('T')


class OneBotJsonPacket(TypedDict):
    action: str
    params: dict
    echo: Optional[str]


class OneBotSegReg(TypedDict):
    type: type
    args: list[str]
