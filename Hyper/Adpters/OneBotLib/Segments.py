import json
import uuid
from Hyper.Errors import *

message_types = {}


def segment_builder(sg_type: str):
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
                    arg[i] = kwargs[i]
            new_arg = arg.copy()

            if len(anns) > len(arg):
                for i in anns.keys():
                    if i not in arg.keys():
                        if i not in var.keys():
                            raise TypeError
                        new_arg[i] = var[i]

            for i in new_arg:
                setattr(self, i, new_arg[i])

        cls.__init__ = init

        def to_json(self) -> dict:
            base = {"type": sg_type, "data": {}}
            for i in anns:
                base["data"][i] = getattr(self, i)

            return base

        cls.to_json = to_json

        message_types[sg_type] = {
            "type": cls,
            "args": list(anns.keys())
        }

        return cls

    return inner_builder


class Base:
    def to_json(self): ...

    def __str__(self) -> str:
        return ""


@segment_builder("text")
class Text(Base):
    text: str

    def __str__(self) -> str:
        return self.text


@segment_builder("image")
class Image(Base):
    file: str
    summary: str = "[图片]"

    def __str__(self) -> str:
        return self.summary or "[图片]"


@segment_builder("at")
class At(Base):
    qq: str

    def __str__(self) -> str:
        return f"@{self.qq}"


@segment_builder("reply")
class Reply(Base):
    id: str

    def __str__(self) -> str:
        return ""


@segment_builder("face")
class Faces(Base):
    id: str

    def __str__(self) -> str:
        return f"[{self.id}]"


@segment_builder("location")
class Location(Base):
    lat: str
    lon: str

    def __str__(self) -> str:
        return f"[位置 {self.lat},{self.lon}]"


@segment_builder("record")
class Record(Base):
    file: str

    def __str__(self) -> str:
        return "[语音]"


@segment_builder("video")
class Video(Base):
    file: str

    def __str__(self) -> str:
        return "[视频]"


@segment_builder("poke")
class Poke(Base):
    type: str
    id: str

    def __str__(self) -> str:
        return "[拍一拍]"


@segment_builder("contact")
class Contact(Base):
    type: str
    id: str

    def __str__(self) -> str:
        return f"[推荐{'群' if self.type == 'group' else '用户'}: {self.id}]"


@segment_builder("forward")
class Forward(Base):
    id: str

    def __str__(self) -> str:
        return "[转发消息]"


@segment_builder("node")
class Node(Base):
    id: str

    def __str__(self) -> str:
        return "[转发消息]"


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


class LongMessage:
    def __init__(self, res_id: str):
        self.content = {"type": "longmsg", "data": {"id": res_id}}

    def set(self, res_id: str) -> None:
        self.__init__(res_id)

    def to_json(self) -> dict:
        return self.content

    def __str__(self) -> str:
        return f"[长消息{self.content['data']['id']}]"


class Json:
    def __init__(self, content: dict):
        self.content = {"type": "json", "data": {"data": json.dumps(content, ensure_ascii=False).replace("'", r'/"')}}

    def set(self, content: dict) -> None:
        self.__init__(content)

    def to_json(self) -> dict:
        return self.content

    def __str__(self) -> str:
        return f"[Json]"

    def __repr__(self) -> str:
        return str(self.content)


@segment_builder("mface")
class MarketFace:
    face_id: str
    tab_id: str
    key: str


@segment_builder("dice")
class Dice:
    pass


@segment_builder("rps")
class Rps:
    pass
