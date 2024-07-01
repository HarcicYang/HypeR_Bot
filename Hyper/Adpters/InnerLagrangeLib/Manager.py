from Hyper import Logic, Configurator, Logger
from Hyper.Logger import levels
from Hyper.Adpters.InnerLagrangeLib.Segments import *
from Hyper.Adpters.InnerLagrangeLib import LagrangeClient
from lagrange.client.events.group import GroupMessage
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

    async def get(self, group_id="", user_id="") -> list:
        ret = []
        for i in self.contents:
            ret.append(await i.get_raw(group_id=group_id, user_id=user_id))
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
    def __init__(self, event_data):
        # n = LagrangeClient.client.get_user_info(event_data.uid)
        self.user_id = event_data.uin
        self.nickname = event_data.nickname
        # if n.sex == 1:
        #     self.sex = "male"
        # elif n.sex == 2:
        #     self.sex = "female"
        # else:
        #     self.sex = "unknown"
        self.sex = "unknown"
        # self.age = n.age
        self.age = 114
        self.card = None
        # self.area = f"{n.country}{n.province}{n.city}"
        self.area = None
        self.level = 0
        self.role = "member"
        self.title = None


def gen_message(data: GroupMessage) -> Message:
    message = Message()
    for i in data.msg_chain:
        if i in message_types:
            if isinstance(i, elems.Quote):
                msg_id = list(LagrangeClient.msg_history.keys())[list(LagrangeClient.msg_history.values()).index(data)]
                message.add(message_types[i]["type"](msg_id))
                continue
            if isinstance(i, elems.At):
                qq = i.uin
                message.add(message_types[i]["type"](qq))
                continue
            args = []
            for j in message_types[i]["args"]:
                args.append(i.__getattribute__(j))
            message.add(message_types[i]["type"](*args))
        else:
            logger.log(f"无法序列化的消息段 {i['type']}", levels.WARNING)

    return message


class Event:
    def __init__(self, data):
        self.post_type = "114514"
        if isinstance(data, GroupMessage):
            self.time = data.time
            self.self_id = 0
            self.post_type = "message"
            self.message_type = "group"
            self.sub_type = "normal"
            lok = list(LagrangeClient.msg_history.keys())
            lov = list(LagrangeClient.msg_history.values())
            self.message_id = lok[lov.index(data)]
            self.group_id = data.grp_id
            self.user_id = data.uin
            self.anonymous = None
            self.message = gen_message(data)
            self.raw_message = data.msg
            self.sender = Sender(data)
            self.is_owner = int(self.user_id) in config.owner
            self.servicing = True if self.user_id in servicing else False
            self.blocked = True if self.user_id in config.black_list or self.group_id in config.black_list else False
            logger.log(
                f"收到 {self.group_id} 由 {self.user_id} 发送的消息: "
                f"{self.message if len(str(self.message)) < 12 else str(self.message)[:12] + '...'}")
            # print(self.message)


class Ret:
    def __init__(self, json_data: dict):
        self.status = json_data["status"]
        self.ret_code = json_data["retcode"]
        self.data = json_data.get("data")
        self.echo = json_data.get("echo")
