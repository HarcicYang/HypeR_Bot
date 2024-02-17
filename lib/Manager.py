from typing import Union
from lib.Segements import *
from lib.Configurator import *
from lib.Logger import Logger

config = Config("./config.json")
logger = Logger()
logger.set_level(config.log_level)


class Message:
    def __init__(self, contents: list[Union[Text, Image, At, Reply, Face, Location]] = None):
        if contents is None:
            contents = []
        self.contents = contents

    def add(self, content: Union[Text, Image, At, Reply, Face, Location]) -> None:
        self.contents.append(content)

    def get(self) -> list:
        ret = []
        for i in self.contents:
            ret.append(i.get_raw())
        return ret

    def __len__(self) -> int:
        return len(self.contents)

    def __getitem__(self, index: int) -> Union[Text, Image, At, Reply, Face, Location]:
        return self.contents[index]

    def __setitem__(self, index: int, content: Union[Text, Image, At, Reply, Face, Location]) -> None:
        self.contents[index] = content

    def __delitem__(self, index: int) -> None:
        del self.contents[index]

    def __iter__(self) -> Union[Text, Image, At, Reply, Face, Location]:
        for i in self.contents:
            yield i

    def __str__(self) -> str:
        return "".join([str(content) for content in self.contents])

    def __repr__(self) -> str:
        return str(self.contents)


class Sender:
    def __init__(self, json_data: dict):
        self.user_id = json_data["user_id"]
        self.nickname = json_data["nickname"]
        self.sex = json_data["sex"]
        self.age = json_data["age"]
        self.card = json_data.get("card")
        self.area = json_data.get("area")
        self.level = json_data.get("level")
        self.role = json_data.get("role")
        self.title = json_data.get("title")


def gen_message(data: dict) -> Message:
    message = Message()
    for i in data["message"]:
        if i["type"] == "text":
            message.add(Text(i["data"]["text"]))
        elif i["type"] == "image":
            message.add(Image(i["data"]["file"]))
        elif i["type"] == "at":
            message.add(At(i["data"]["qq"]))
        elif i["type"] == "reply":
            message.add(Reply(i["data"]["id"]))
        elif i["type"] == "face":
            message.add(Face(i["data"]["id"]))
        elif i["type"] == "location":
            message.add(Location(i["data"]["lat"], i["data"]["lon"]))
    return message


class Event:
    def __init__(self, data: dict):
        self.time = data["time"]
        self.self_id = data["self_id"]
        self.post_type = data["post_type"]
        if self.post_type == "message":
            self.message_type = data["message_type"]
            self.sub_type = data["sub_type"]
            self.message_id = str(data["message_id"])
            self.user_id = data["user_id"]
            self.group_id = data.get("group_id")
            self.sender = Sender(data["sender"])
            self.message = gen_message(data)
            logger.log(
                f"收到 {self.group_id} 由 {self.user_id} 发送的消息: {self.message if len(str(self.message)) < 5 else str(self.message)[:5] + '...'}")

        elif self.post_type == "notice":
            self.notice_type = data["notice_type"]
            self.sub_type = data["sub_type"]
            self.group_id = data.get("group_id")
            self.operator_id = data.get("operator_id")
            self.user_id = data["user_id"]

        self.is_owner = int(self.user_id) in config.owner


class Ret:
    def __init__(self, json_data: dict):
        self.status = json_data["status"]
        self.ret_code = json_data["retcode"]
        self.data = json_data.get("data")
        self.echo = json_data.get("echo")
