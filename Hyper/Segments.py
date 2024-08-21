import json
import os.path
import typing
import uuid

from Hyper.Utils.Errors import *
from Hyper.Configurator import cm

config = cm.get_cfg()
if config.protocol == "OneBot":
    from Hyper.Adapters.OneBotLib.Res import segment_builder, Base, message_types
elif config.protocol == "Satori":
    # from Hyper.Adapters.SatoriLib.Res import segment_builder, Base, message_types
    pass


class MediaSeg(Base):
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


@segment_builder("text", "<text>")
class Text(Base):
    text: str


@segment_builder("image", "[图片]")
class Image(MediaSeg):
    file: str
    url: str
    summary: str = "[图片]"


@segment_builder("at", f"@<qq>")
class At(Base):
    qq: str


@segment_builder("reply", "")
class Reply(Base):
    id: str


@segment_builder("face", "[表情: <id>]")
class Faces(Base):
    id: str


@segment_builder("location", "[位置: <lat>, <lon>]")
class Location(Base):
    lat: str
    lon: str


@segment_builder("record", "[语音]")
class Record(MediaSeg):
    file: str
    url: str


@segment_builder("video", "[视频]")
class Video(MediaSeg):
    file: str
    url: str


@segment_builder("poke", "[拍一拍]")
class Poke(Base):
    type: str
    id: str


@segment_builder("contact")
class Contact(Base):
    type: str
    id: str

    def __str__(self) -> str:
        return f"[推荐{'群' if self.type == 'group' else '用户'}: {self.id}]"


@segment_builder("forward", "[转发消息]")
class Forward(Base):
    id: str


@segment_builder("node", "[转发消息]")
class Node(Base):
    id: str


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


@segment_builder("longmsg", "[<id>]")
class LongMessage(Base):
    id: str


@segment_builder("json", "[Json]")
class Json(Base):
    data: typing.Union[dict, list, str]


@segment_builder("mface", "[表情]")
class MarketFace(Base):
    face_id: str
    tab_id: str
    key: str


@segment_builder("dice", "[骰子]")
class Dice(Base):
    pass


@segment_builder("rps", "[猜拳]")
class Rps(Base):
    pass


@segment_builder("music", "[音乐]")
class Music(Base):
    type: str
    id: str = None
    url: str
    audio: str = None
    title: str = None
