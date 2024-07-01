from Hyper import Logic, Configurator, Logger
from Hyper.Logger import levels
from Hyper.Adpters.OneBotLib.Segments import *

config = Configurator.Config("./config.json")
logger = Logger.Logger()
logger.set_level(config.log_level)

servicing = []


class Message:
    def __init__(self, contents: list = None):
        if contents is None:
            contents = []
        self.contents = contents

    def add(self, content) -> None:
        self.contents.append(content)

    async def get(self) -> list:
        ret = []
        for i in self.contents:
            ret.append(i.get_raw())
        return ret

    def get_sync(self) -> list:
        ret = []
        for i in self.contents:
            ret.append(i.get_raw())
        return ret

    def __len__(self) -> int:
        return len(self.contents)

    def __getitem__(self, index: int):
        return self.contents[index]

    def __setitem__(self, index: int, content) -> None:
        self.contents[index] = content

    def __delitem__(self, index: int) -> None:
        del self.contents[index]

    def __iter__(self):
        for i in self.contents:
            yield i

    def __str__(self) -> str:
        return "".join([str(content) for content in self.contents])

    def __repr__(self) -> str:
        return str(self.contents)

    def __add__(self, new):
        self.contents += new.contents
        return self

    def __iadd__(self, new):
        self.contents += new.contents
        return self


class Sender:
    def __init__(self, json_data: dict):
        self.user_id = json_data.get("user_id")
        self.nickname = json_data.get("nickname")
        self.sex = json_data.get("sex")
        self.age = json_data.get("age")
        self.card = json_data.get("card")
        self.area = json_data.get("area")
        self.level = json_data.get("level")
        self.role = json_data.get("role")
        self.title = json_data.get("title")


def gen_message(data: dict) -> Message:
    message = Message()
    for i in data["message"]:
        if i["type"] in message_types:
            args = []
            for j in message_types[i["type"]]["args"]:
                args.append(i["data"].get(j))
            message.add(message_types[i["type"]]["type"](*args))
        else:
            logger.log(f"无法序列化的消息段 {i['type']}", levels.WARNING)

    return message


class Event:
    def __init__(self, data: dict):
        self.time = data.get("time")
        self.self_id = data.get("self_id")
        self.post_type = data.get("post_type")
        if self.post_type == "message":
            self.message_type = data.get("message_type")
            self.sub_type = data.get("sub_type")
            self.message_id = str(data.get("message_id"))
            self.user_id = data.get("user_id")
            self.group_id = data.get("group_id")
            self.sender = Sender(data.get("sender"))
            self.message = gen_message(data=data)
            logger.log(
                f"收到 {self.group_id} 由 {self.user_id} 发送的消息: "
                f"{self.message if len(str(self.message)) < 12 else str(self.message)[:12] + '...'}")

        elif self.post_type == "notice":
            self.notice_type = data.get("notice_type")
            self.sub_type = data.get("sub_type")
            self.group_id = data.get("group_id")
            self.operator_id = data.get("operator_id")
            self.user_id = data.get("user_id")

        elif self.post_type == "request":
            self.request_type = data.get("request_type")
            self.sub_type = data.get("sub_type")
            self.user_id = data.get("user_id")
            self.group_id = data.get("group_id")
            self.comment = data.get("comment")
            self.flag = data.get("flag")
            logger.log(
                f"收到 {self.group_id} 由 {self.user_id} 发送的{'加群请求' if self.sub_type == 'add' else '邀请加群'}: {self.comment}")

        self.is_owner = int(self.user_id) in config.owner
        self.servicing = True if self.user_id in servicing else False
        self.blocked = True if self.user_id in config.black_list or self.group_id in config.black_list else False


class Ret:
    def __init__(self, json_data: dict):
        self.status = json_data["status"]
        self.ret_code = json_data["retcode"]
        self.data = json_data.get("data")
        self.echo = json_data.get("echo")
