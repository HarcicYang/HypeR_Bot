import json
import typing
import uuid

from Hyper.Errors import *

message_types = {}


def segment_builder(sg_type: str, summary_tmp: str = None):
    # print(inspect.get_annotations(cls))
    def inner_builder(cls):
        var = dict(vars(cls))
        anns: dict = var.get("__annotations__", False) or dict()
        arg = {}

        def init(self, *args, **kwargs):
            if len(args) > 0:
                for i in args:
                    arg[list(anns.keys())[list(args).index(i)]] = i

            if len(kwargs) > 0:
                for i in kwargs:
                    try:
                        arg[i] = anns[i](kwargs[i])
                    except TypeError:
                        arg[i] = kwargs[i]
            new_arg = arg.copy()

            if len(anns) > len(arg):
                for i in anns.keys():
                    if i not in arg.keys():
                        if i not in var.keys():
                            new_arg[i] = None
                            continue
                        if not isinstance(var[i], anns[i]):
                            new_arg[i] = anns[i](var[i])
                        else:
                            new_arg[i] = var[i]

            for i in new_arg:
                setattr(self, i, new_arg[i])

        cls.__init__ = init

        def to_json(self) -> dict:
            base = {"type": sg_type, "data": {}}
            for i in anns:
                if not isinstance(getattr(self, i), anns[i]):
                    base["data"][i] = anns[i](getattr(self, i))
                else:
                    base["data"][i] = getattr(self, i)
                # try:
                #     base["data"][i] = anns[i](getattr(self, i))
                # except TypeError:
                #     base["data"][i] = getattr(self, i)
            return base

        cls.to_json = to_json

        def to_str(self) -> str:
            text = summary_tmp
            if text is None:
                text = "[]"
            if "<" not in text and ">" not in text:
                return text

            for i in anns:
                if f"<{i}>" in summary_tmp:
                    try:
                        v = self.__getattribute__(i)
                    except AttributeError:
                        v = None
                    text = text.replace(f"<{i}>", str(v))

            return text

        cls.__str__ = to_str if cls().__str__() == "__not_set__" else cls.__str__

        message_types[sg_type] = {
            "type": cls,
            "args": list(anns.keys())
        }

        return cls

    return inner_builder


class Base:
    def __init__(self, *args, **kwargs): ...

    def to_json(self) -> dict: ...

    def __str__(self) -> str: return "__not_set__"


@segment_builder("text", "<text>")
class Text(Base):
    text: str


@segment_builder("image", "[图片]")
class Image(Base):
    file: str
    url: str = ""
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
class Record(Base):
    file: str


@segment_builder("video", "[视频]")
class Video(Base):
    file: str


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
    url: str = None
    audio: str = None
    title: str = None
