from Hyper import Configurator, Logger, Manager
from Hyper.Segments import message_types
from Hyper.Logger import levels

config = Configurator.Config("config.json")
logger = Logger.Logger()
logger.set_level(config.log_level)


class EventManager:
    def __init__(self):
        self.event_lis = {
            "message": {},
            "notice": {},
            "request": {}
        }

    def reg(self, type_of: str, str_eql: str) -> callable:
        def wrapper(cls):
            self.event_lis[type_of][str_eql] = cls
            return cls

        return wrapper

    def new(self, data: dict) -> "Event":
        return self.event_lis[data["post_type"]][data[f"{data['post_type']}_type"]](data)


em = EventManager()


class GroupSender:
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


class PrivateSender:
    def __init__(self, json_data: dict):
        self.user_id = json_data.get("user_id")
        self.nickname = json_data.get("nickname")
        self.sex = json_data.get("sex")
        self.age = json_data.get("age")


class GroupAnonymous:
    def __init__(self, json_data: dict):
        if json_data is None:
            pass
        else:
            self.id = json_data.get("id")
            self.name = json_data.get("name")
            self.flag = json_data.get("flag")


def gen_message(data: dict) -> Manager.Message:
    message = Manager.Message()
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
        self.data = data
        self.time = data.get("time")
        self.self_id = data.get("self_id")
        self.post_type = data.get("post_type")
        self.user_id = data.get("user_id")
        self.group_id = data.get("group_id")

        self.is_owner = int(self.user_id) in config.owner
        self.servicing = False
        self.blocked = True if self.user_id in config.black_list or self.group_id in config.black_list else False
        self.is_silent = self.user_id in config.silents or self.group_id in config.silents or 0 in config.silents

    def print_log(self, **kwargs) -> None:
        ...


class MessageEvent(Event):
    def __init__(self, data: dict):
        super().__init__(data)
        self.sub_type = data.get("sub_type")
        self.message_id = str(data.get("message_id"))
        self.message = gen_message(data=data)


@em.reg("message", "private")
class PrivateMessageEvent(MessageEvent):
    def __init__(self, data: dict):
        super().__init__(data)
        self.sender = PrivateSender(data.get("sender"))

        data["message"] = self.message
        self.print_log(**data)

    @Logger.AutoLog.register(Logger.AutoLog.templates().on_message, logger)
    def print_log(self, **kwargs) -> None:
        pass


@em.reg("message", "group")
class GroupMessageEvent(MessageEvent):
    def __init__(self, data: dict):
        super().__init__(data)
        self.sender = GroupSender(data.get("sender"))
        self.anonymous = GroupAnonymous(data.get("anonymous"))

        data["message"] = self.message
        self.print_log(**data)

    @Logger.AutoLog.register(Logger.AutoLog.templates().on_message, logger)
    def print_log(self, **kwargs) -> None:
        pass


class NoticeEvent(Event):
    def __init__(self, data: dict):
        super().__init__(data)
        self.notice_type = data.get("notice_type")


@em.reg("notice", "group_upload")
class GroupFileUploadEvent(NoticeEvent):
    def __init__(self, data: dict):
        super().__init__(data)
        self.file = data.get("file")

        self.print_log(**data)

    @Logger.AutoLog.register(Logger.AutoLog.templates().on_notice, logger)
    def print_log(self, **kwargs) -> None:
        pass


@em.reg("notice", "group_admin")
class GroupAdminEvent(NoticeEvent):
    def __init__(self, data: dict):
        super().__init__(data)
        self.sub_type = data.get("sub_type")

        self.print_log(**data)

    @Logger.AutoLog.register(Logger.AutoLog.templates().on_notice, logger)
    def print_log(self, **kwargs) -> None:
        pass


@em.reg("notice", "group_decrease")
class GroupMemberDecreaseEvent(NoticeEvent):
    def __init__(self, data: dict):
        super().__init__(data)
        self.sub_type = data.get("sub_type")
        self.operator_id = data.get("operator_id")

        self.print_log(**data)

    @Logger.AutoLog.register(Logger.AutoLog.templates().on_notice, logger)
    def print_log(self, **kwargs) -> None:
        pass


@em.reg("notice", "group_increase")
class GroupMemberIncreaseEvent(NoticeEvent):
    def __init__(self, data: dict):
        super().__init__(data)
        self.sub_type = data.get("sub_type")
        self.operator_id = data.get("operator_id")

        self.print_log(**data)

    @Logger.AutoLog.register(Logger.AutoLog.templates().on_notice, logger)
    def print_log(self, **kwargs) -> None:
        pass


@em.reg("notice", "group_ban")
class GroupMuteEvent(NoticeEvent):
    def __init__(self, data: dict):
        super().__init__(data)
        self.sub_type = data.get("sub_type")
        self.operator_id = data.get("operator_id")
        self.duration = data.get("duration")

        self.print_log(**data)

    @Logger.AutoLog.register(Logger.AutoLog.templates().on_notice, logger)
    def print_log(self, **kwargs) -> None:
        pass


@em.reg("notice", "friend_add")
class FriendAddEvent(NoticeEvent):
    def __init__(self, data: dict):
        super().__init__(data)

        self.print_log(**data)

    @Logger.AutoLog.register(Logger.AutoLog.templates().on_notice, logger)
    def print_log(self, **kwargs) -> None:
        pass


@em.reg("notice", "group_recall")
class GroupRecallEvent(NoticeEvent):
    def __init__(self, data: dict):
        super().__init__(data)
        self.operator_id = data.get("operator_id")
        self.message_id = data.get("message_id")

        self.print_log(**data)

    @Logger.AutoLog.register(Logger.AutoLog.templates().on_notice, logger)
    def print_log(self, **kwargs) -> None:
        pass


@em.reg("notice", "friend_recall")
class FriendRecallEvent(NoticeEvent):
    def __init__(self, data: dict):
        super().__init__(data)
        self.operator_id = data.get("operator_id")
        self.message_id = data.get("message_id")

        self.print_log(**data)

    @Logger.AutoLog.register(Logger.AutoLog.templates().on_notice, logger)
    def print_log(self, **kwargs) -> None:
        pass


@em.reg("notice", "notify")
class NotifyEvent(Event):
    def __init__(self, data: dict):
        super().__init__(data)
        self.sub_type = data.get("sub_type")
        self.target_id = data.get("target_id")
        self.honor_type = data.get("honor_type")

        self.print_log(**data)

    @Logger.AutoLog.register(Logger.AutoLog.templates().on_notice, logger)
    def print_log(self, **kwargs) -> None:
        pass


class RequestEvent(Event):
    def __init__(self, data: dict):
        super().__init__(data)
        self.comment = data.get("comment")
        self.flag = data.get("flag")


@em.reg("request", "friend")
class FriendAddEvent(RequestEvent):
    def __init__(self, data: dict):
        super().__init__(data)

        self.print_log(**data)

    @Logger.AutoLog.register(Logger.AutoLog.templates().on_notice, logger)
    def print_log(self, **kwargs) -> None:
        pass


@em.reg("request", "group")
class GroupAddInviteEvent(RequestEvent):
    def __init__(self, data: dict):
        super().__init__(data)
        self.sub_type = data.get("sub_type")

        self.print_log(**data)

    @Logger.AutoLog.register(Logger.AutoLog.templates().on_notice, logger)
    def print_log(self, **kwargs) -> None:
        pass


