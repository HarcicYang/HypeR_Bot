import json
import os.path
import typing
import uuid

from .utils.errors import *
from .utils.hypetyping import Union
from . import configurator

config = configurator.BotConfig.get("hyper-bot")
if config.protocol == "OneBot":
    # from Hyper.Adapters.OneBotLib.Res import segment_builder, Base, message_types
    from .Adapters.OneBotLib.Res import SegmentBase, message_types
elif config.protocol == "Satori":
    # from Hyper.Adapters.SatoriLib.Res import segment_builder, Base, message_types
    raise NotImplementedError()
elif config.protocol == "Lagrange":
    # from Hyper.Adapters.LagrangeLib.Res import segment_builder, Base, message_types
    raise NotImplementedError()
elif config.protocol == "Kritor":
    # from Hyper.Adapters.KritorLib.Res import segment_builder, Base, message_types
    from .Adapters.KritorLib.Res import SegmentBase, message_types


class MediaSeg(SegmentBase):
    @classmethod
    def build(cls, file: str):
        if file.startswith("http") or file.startswith("file:") or file.startswith("base64:"):
            return cls(file=file)
        else:
            if os.path.isfile(file):
                if os.path.isabs(file):
                    res = cls()
                    res.file = f"file://{file}"
                    return res
                else:
                    res = cls()
                    res.file = f"file://{os.path.abspath(file)}"
                    return res
            else:
                return None

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)


class Text(SegmentBase, st="text", su="<text>"):
    text: str


class StreamTest(SegmentBase, st="stream", su="[Stream] <text>"):
    text: str

class Image(MediaSeg, st="image", su="[Image]"):
    file: str
    url: str
    summary: str = "[Image]"


class At(SegmentBase, st="at", su=f"@<qq>"):
    qq: str


class Reply(SegmentBase, st="reply", su=""):
    id: str


class Faces(SegmentBase, st="face", su="[Face: <id>]"):
    id: str


# @segment_builder("location", "[位置: <lat>, <lon>]")
# class Location(Base):
#     lat: str
#     lon: str


class Record(MediaSeg, st="record", su="[Audio]"):
    file: str
    url: str


class Video(MediaSeg, st="video", su="[Video]"):
    file: str
    url: str


class Poke(SegmentBase, st="poke", su="[Poke]"):
    type: str
    id: str


class Contact(SegmentBase, st="contact"):
    type: str
    id: str

    def __str__(self) -> str:
        return f"[推荐{'群' if self.type == 'group' else '用户'}: {self.id}]"


class Forward(SegmentBase, st="forward", su="[Forward]"):
    id: str


class Node(SegmentBase, st="node", su="[Node]"):
    user_id: str
    nickname: str
    content: Union[dict, "common.Message"]


class CustomNode:
    def __init__(self, user_id: str, nick_name: str, content):
        self.content = {"type": "node",
                        "data": {"user_id": user_id, "nick_name": nick_name, "content": content.get_sync()}}

    def to_json(self) -> dict:
        return self.content

    def __str__(self) -> str:
        return f"[自定义节点]"


class KeyBoardButton:
    def __init__(self,
                 text: str,
                 style: int = 1,
                 button_type: int = 2,
                 data: str = "Hello World",
                 enter: bool = False,
                 permission: int = 2,
                 specify_user_ids=None):
        self.content = {
            "id": str(uuid.uuid4()),
            "render_data": {
                "label": text,
                "visited_label": text,
                "style": style
            },
            "action": {
                "type": button_type,
                "permission": {
                    "type": permission,
                    "specify_user_ids": specify_user_ids
                },
                "enter": enter,
                "unsupport_tips": "Harcic",
                "data": data
            }
        }

    def get(self) -> dict:
        return self.content

    def __str__(self) -> str:
        return f"[按键{self.content['render_data']['label']}]"


class KeyBoardRow:
    def __init__(self, buttons: list[KeyBoardButton] = None):
        self.content = {
            "buttons": []
        }
        buttons = [] if buttons is None else buttons
        for i in buttons:
            self.content["buttons"].append(i.get())

    def add(self, button: KeyBoardButton) -> None:
        if len(self.content["buttons"]) < 5:
            self.content["buttons"].append(button.get())
        else:
            raise ButtonRowFulledError("This button row is full")

    def get(self) -> dict:
        return self.content


class KeyBoard:
    def __init__(self, button_rows: list[KeyBoardRow]):
        self.content = {"type": "keyboard",
                        "data": {"content": {"rows": [i.get() for i in button_rows]}, "bot_appid": 0}}

    def to_json(self) -> dict:
        return self.content

    def __str__(self) -> str:
        return f"[自定按键版]"


class MarkdownContent:
    def __init__(self, raw_content: str):
        self.content = (
            raw_content
            .replace('"', r'\\\"')
            .replace(r"\`", r"\`")
        )


class MarkDown:
    def __init__(self, content: MarkdownContent):
        self.content = {"type": "markdown",
                        "data": {"content": json.dumps({"content": content.content}).replace('"', '"')}}

    def set(self, content: MarkdownContent) -> None:
        self.__init__(content)

    def to_json(self) -> dict:
        return self.content

    def __str__(self) -> str:
        return f"[MarkDown]"


# @segment_builder("longmsg", "[<id>]")
class LongMessage(SegmentBase, st="longmsg", su="[Long: <id>]"):
    id: str


# @segment_builder("json", "[Json]")
class Json(SegmentBase, st="json", su="[Json]"):
    data: typing.Union[dict, list, str]


# @segment_builder("mface", "[表情]")
class MarketFace(SegmentBase, st="mface", su=""):
    face_id: str
    tab_id: str
    key: str


# @segment_builder("dice", "[骰子]")
class Dice(SegmentBase, st="dice", su="[Dice]"):
    pass


# @segment_builder("rps", "[猜拳]")
class Rps(SegmentBase, st="rps", su="[RPS]"):
    pass


# @segment_builder("music", "[音乐]")
class Music(SegmentBase, st="music", su="[Music]"):
    type: str
    id: str = None
    url: str
    audio: str = None
    title: str = None
