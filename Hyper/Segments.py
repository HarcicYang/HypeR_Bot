import json
import uuid
from Hyper.Errors import *


class Text:
    def __init__(self, text: str):
        self.content = {"type": "text", "data": {"text": text}}

    def set(self, text: str) -> None:
        self.__init__(text)

    def get(self) -> str:
        return self.content["data"]["text"]

    def get_raw(self) -> dict:
        return self.content

    def __str__(self) -> str:
        return self.content["data"]["text"]

    def __repr__(self) -> str:
        return str(self.content)


class Image:
    def __init__(self, image: str, summary: str = "[图片]"):
        self.content = {"type": "image", "data": {"file": image, "summary": summary}}

    def set(self, image: str, summary: str = "[图片]") -> None:
        self.__init__(image, summary)

    def get(self) -> str:
        return self.content["data"]["file"]

    def get_raw(self) -> dict:
        return self.content

    def __str__(self) -> str:
        return "[图片]"

    def __repr__(self) -> str:
        return str(self.content)


class At:
    def __init__(self, user_id: str):
        self.content = {"type": "at", "data": {"qq": str(user_id)}}

    def set(self, user_id: str) -> None:
        self.__init__(user_id)

    def get(self) -> str:
        return self.content["data"]["qq"]

    def get_raw(self) -> dict:
        return self.content

    def __str__(self) -> str:
        return f"@{self.content['data']['qq']} "

    def __repr__(self) -> str:
        return str(self.content)


class Reply:
    def __init__(self, message_id: str):
        self.content = {"type": "reply", "data": {"id": message_id}}

    def set(self, message_id: str) -> None:
        self.__init__(message_id)

    def get(self) -> str:
        return self.content["data"]["id"]

    def get_raw(self) -> dict:
        return self.content

    def __str__(self) -> str:
        return f"[回复{self.content['data']['id']}]"

    def __repr__(self) -> str:
        return str(self.content)


class Face:
    def __init__(self, face_id: str):
        self.content = {"type": "face", "data": {"id": face_id}}

    def set(self, face_id: str) -> None:
        self.__init__(face_id)

    def get(self) -> str:
        return self.content["data"]["id"]

    def get_raw(self) -> dict:
        return self.content

    def __str__(self) -> str:
        return "[表情]"

    def __repr__(self) -> str:
        return str(self.content)


class Location:
    def __init__(self, lat: str, lon: str):
        self.content = {"type": "location", "data": {"lat": lat, "lon": lon}}

    def set(self, lat: str, lon: str) -> None:
        self.__init__(lat, lon)

    def get(self) -> tuple[str, str]:
        return self.content["data"]["lat"], self.content["data"]["lon"]

    def get_raw(self) -> dict:
        return self.content

    def __str__(self) -> str:
        return f"[位置{self.content['data']['lat']}, {self.content['data']['lon']}]"

    def __repr__(self) -> str:
        return str(self.content)


class Record:
    def __init__(self, record: str):
        self.content = {"type": "record", "data": {"file": record}}

    def set(self, record: str) -> None:
        self.__init__(record)

    def get(self) -> str:
        return self.content["data"]["file"]

    def get_raw(self) -> dict:
        return self.content

    def __str__(self) -> str:
        return "[语音]"

    def __repr__(self) -> str:
        return str(self.content)


class Video:
    def __init__(self, video: str):
        self.content = {"type": "video", "data": {"file": video}}

    def set(self, video: str) -> None:
        self.__init__(video)

    def get(self) -> str:
        return self.content["data"]["file"]

    def get_raw(self) -> dict:
        return self.content

    def __str__(self) -> str:
        return "[视频]"

    def __repr__(self) -> str:
        return str(self.content)


class Poke:
    def __init__(self, poke_type: str, poke_id: str):
        self.content = {"type": "poke", "data": {"type": poke_type, "id": poke_id}}

    def set(self, poke_type: str, poke_id: str) -> None:
        self.__init__(poke_type, poke_id)

    def get(self) -> None:
        raise NotSupportError("This type of message cannot use '.get()'")

    def get_raw(self) -> dict:
        return self.content

    def __str__(self) -> str:
        return "[戳一戳]"

    def __repr__(self) -> str:
        return str(self.content)


class Contact:
    def __init__(self, platform: str, target_id: str):
        self.content = {"type": "contact", "data": {"type": platform, "id": target_id}}

    def set(self, platform: str, target_id: str) -> None:
        self.__init__(platform, target_id)

    def get(self) -> str:
        raise NotSupportError("This type of message cannot use '.get()'")

    def get_raw(self) -> dict:
        return self.content

    def __str__(self) -> str:
        return f"[推荐QQ{'用户' if self.content['data']['type'] == 'qq' else '群'}{self.content['data']['id']}]"

    def __repr__(self) -> str:
        return str(self.content)


class Forward:
    def __init__(self, res_id: str):
        self.content = {"type": "forward", "data": {"id": res_id}}

    def set(self, res_id: str) -> None:
        self.__init__(res_id)

    def get(self) -> str:
        return self.content["data"]["id"]

    def get_raw(self) -> dict:
        return self.content

    def __str__(self) -> str:
        return f"[转发消息]"

    def __repr__(self) -> str:
        return str(self.content)


class Node:
    def __init__(self, node_id: str):
        self.content = {"type": "node", "data": {"id": node_id}}

    def set(self, node_id: str) -> None:
        self.__init__(node_id)

    def get(self) -> str:
        return self.content["data"]["id"]

    def get_raw(self) -> dict:
        return self.content

    def __str__(self) -> str:
        return f"[节点{self.content['data']['id']}]"

    def __repr__(self) -> str:
        return str(self.content)


class CustomNode:
    def __init__(self, user_id: str, nick_name: str, content):
        self.content = {"type": "node",
                        "data": {"user_id": user_id, "nick_name": nick_name, "content": content.get()}}

    def set(self, user_id: str, nick_name: str, content) -> None:
        self.__init__(user_id, nick_name, content)

    def get(self) -> list:
        return self.content["data"]["content"]

    def get_raw(self) -> dict:
        return self.content

    def __str__(self) -> str:
        return f"[自定义节点]"

    def __repr__(self) -> str:
        return str(self.content)


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

    def set(self,
            text: str,
            style: int = 1,
            button_type: int = 2,
            data: str = "Hello World",
            enter: bool = False,
            permission: int = 2,
            specify_user_ids=None) -> None:
        self.__init__(text, style, button_type, data, enter, permission, specify_user_ids)

    def get(self) -> dict:
        return self.content

    def __str__(self) -> str:
        return f"[按键{self.content['render_data']['label']}]"

    def __repr__(self) -> str:
        return str(self.content)


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

    def set(self, button_rows: list[KeyBoardRow]) -> None:
        self.__init__(button_rows)

    def get(self) -> dict:
        return self.content["data"]["content"]

    def get_raw(self) -> dict:
        return self.content

    def __str__(self) -> str:
        return f"[自定按键版]"

    def __repr__(self) -> str:
        return str(self.content)


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

    def get(self) -> str:
        return json.loads(self.content["data"]["content"])["content"]

    def get_raw(self) -> dict:
        return self.content

    def __str__(self) -> str:
        return f"[MarkDown]"

    def __repr__(self) -> str:
        return str(self.content)


class LongMessage:
    def __init__(self, res_id: str):
        self.content = {"type": "longmsg", "data": {"id": res_id}}

    def set(self, res_id: str) -> None:
        self.__init__(res_id)

    def get(self) -> str:
        return self.content["data"]["id"]

    def get_raw(self) -> dict:
        return self.content

    def __str__(self) -> str:
        return f"[长消息{self.content['data']['id']}]"

    def __repr__(self) -> str:
        return str(self.content)


class Json:
    def __init__(self, content: dict):
        self.content = {"type": "json", "data": {"data": json.dumps(content, ensure_ascii=False).replace("'", r'/"')}}

    def set(self, content: dict) -> None:
        self.__init__(content)

    def get(self) -> dict:
        return json.loads(self.content["data"]["data"])

    def get_raw(self) -> dict:
        return self.content

    def __str__(self) -> str:
        return f"[Json]"

    def __repr__(self) -> str:
        return str(self.content)


class MarketFace:
    def __init__(self, face_id: str, tab_id: str, key: str):
        self.content = {"type": "marketface", "data": {"face_id": face_id, "tab_id": tab_id, "key": key}}

    def set(self, face_id: str, tab_id: str, key: str) -> None:
        self.__init__(face_id, tab_id, key)

    def get(self) -> str:
        return self.content["data"]["face_id"]

    def get_raw(self) -> dict:
        return self.content

    def __str__(self) -> str:
        return ""

    def __repr__(self) -> str:
        return str(self.content)


class Dice:
    def __init__(self):
        self.content = {"type": "dice", "data": {}}

    def get_raw(self) -> dict:
        return self.content

    def __str__(self) -> str:
        return "[骰子]"

    def __repr__(self) -> str:
        return str(self.content)


class Rps:
    def __init__(self):
        self.content = {"type": "rps", "data": {}}

    def get_raw(self) -> dict:
        return self.content

    def __str__(self) -> str:
        return "[猜拳]"

    def __repr__(self) -> str:
        return str(self.content)


message_types = {
    "text": {
        "type": Text,
        "args": [
            "text"
        ]
    },
    "image": {
        "type": Image,
        "args": [
            "file"
        ]
    },
    "at": {
        "type": At,
        "args": [
            "qq"
        ]
    },
    "reply": {
        "type": Reply,
        "args": [
            "id"
        ]
    },
    "face": {
        "type": Face,
        "args": [
            "id"
        ]
    },
    "location": {
        "type": Location,
        "args": [
            "lat",
            "lon"
        ]
    },
    "record": {
        "type": Record,
        "args": [
            "file"
        ]
    },
    "video": {
        "type": Video,
        "args": [
            "file"
        ]
    },
    "node": {
        "type": Node,
        "args": [
            "id"
        ]
    },
    "contact": {
        "type": Contact,
        "args": [
            "type",
            "id"
        ]
    },
    "forward": {
        "type": Forward,
        "args": [
            "id"
        ]
    },
    "poke": {
        "type": Poke,
        "args": [
            "type",
            "id"
        ]
    },
    "marketface": {
        "type": MarketFace,
        "args": [
            "face_id",
            "tab_id",
            "key"
        ]
    },
    "dice": {
        "type": Dice,
        "args": []
    },
    "rps": {
        "type": Rps,
        "args": []
    }
}
