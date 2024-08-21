import datetime
import typing
import inspect
from functools import wraps


class Levels:
    def __init__(self):
        self.TRACE = f"✔️ \033[{47}m\033[{30}mTRACE \033[0m\033[0m "
        self.INFO = f"ℹ️ \033[{47}m\033[{30}mINFO \033[0m\033[0m "
        self.WARNING = f"⚠️ \033[{43}mWARN \033[0m "
        self.ERROR = f"❌ \033[{41}mERROR\033[0m "
        self.CRITICAL = f"🔴 \033[{41};{1}m*CRIT\033[0m "
        self.DEBUG = f"🛠️ \033[{43}mDEBUG\033[0m "

        self.level_nums = {
            self.TRACE: -1,
            self.INFO: 0,
            self.WARNING: 1,
            self.ERROR: 2,
            self.CRITICAL: 3,
            self.DEBUG: 10,
        }

        self.level_names = {
            "TRACE": self.TRACE,
            "INFO": self.INFO,
            "WARNING": self.WARNING,
            "ERROR": self.ERROR,
            "CRITICAL": self.CRITICAL,
            "DEBUG": self.DEBUG,
        }


levels = Levels()


class Logger:
    def __init__(self):
        self.log_level = levels.INFO

    def set_level(self, level: str):
        if level in levels.level_names:
            self.log_level = levels.level_names[level]
        else:
            self.log("未知的日志等级", levels.ERROR)

    def log(self, message: str, level: str = levels.INFO):
        if levels.level_nums[level] < levels.level_nums[self.log_level]:
            return
        time = datetime.datetime.now()
        if "\n" in message:
            listed = message.split("\n")
            for i in listed:
                content = f" \033[38;5;244m[{str(time)[:-4]}]\033[0m {level} {i}"
                print(content)
        else:
            content = f" \033[38;5;244m[{str(time)[:-4]}]\033[0m {level} {message}"
            print(content)


class AutoLog:
    def __init__(self, func: callable, template: str, logger: Logger, level: str = levels.INFO):
        self.func = func
        self.template = template
        self.logger = logger
        self.level = level

    @staticmethod
    def templates(lang: str = "zh_CN"):
        class Base:
            on_message: str
            on_notice: str
            on_request: str
            send: str
            recall: str
            kick: str
            mute: str
            unmute: str
            set_req: str
            set_ess: str

        if lang == "zh_CN":
            class Templates(Base):
                on_message = "收到群 <group_id> 中 <user_id> 的消息：<message>"
                on_notice = "在 <group_id> 中 <operator_id> 对 <user_id> 进行了 <notice_type>/<sub_type> 操作"
                on_request = "在群 <group_id> 收到来自 <user_id> 的 <request_type>/<sub_type> 请求"
                send = "向群 <group_id> 用户 <user_id> 发送消息：<message>"
                recall = "撤回消息 <message_id>"
                kick = "将 <user_id> 踢出 <group_id>"
                mute = "将 <user_id> 在 <group_id> 禁言 <duration> 秒"
                unmute = "将 <user_id> 在 <group_id> 解除禁言"
                set_req = "处理 <sub_type> 请求 <flag> 的结果为 <approve>"
                set_ess = "将 <message_id> 设为精华"
        else:
            class Templates(Base):
                on_message = "Msg received in grp <group_id> from <user_id> : <message>"
                on_notice = "<operator_id> acted '<notice_type>/<sub_type>' to <user_id> in <group_id>"
                on_request = "Received '<request_type>/<sub_type>' request from <user_id> in <group_id>"
                send = "Sent a msg in grp <group_id> to <user_id> : <message>"
                recall = "Deleted <message_id>"
                kick = "kicked <user_id> out of <group_id>"
                mute = "Muted <user_id> in <group_id> for <duration>s"
                unmute = "Unmuted <user_id> in <group_id>"
                set_req = "Resulted <sub_type>/<flag> as <approve>"
                set_ess = "Pinned msg <message_id>"

        return Templates

    def __rel_tpl(self, args: dict) -> str:
        log = self.template
        for i in args:
            if f"<{i}>" in log:
                log = log.replace(f"<{i}>", str(args[i]))
        return log

    @classmethod
    def register(cls, *args, **kwargs) -> callable:
        def create(func):
            @wraps(func)
            def wrapper(*args_, **kwargs_):
                return cls(func, *args, **kwargs)(*args_, **kwargs_)

            return wrapper

        return create

    def handler(self, res, *args, **kwargs) -> typing.Any:
        sig = inspect.signature(self.func)
        argv = {}

        if len(list(args)) > 0:
            sigs = list(sig.parameters.items())
            for i in list(args):
                index = list(args).index(i)
                argv[sigs[index][0]] = i

        if len(kwargs) > 0:
            for i in kwargs:
                argv[i] = kwargs[i]

        log = self.__rel_tpl(argv)
        self.logger.log(log, level=self.level)

        return res

    def __call__(self, *args, **kwargs) -> typing.Any:
        res = self.func(*args, **kwargs)
        return self.handler(res, *args, **kwargs)


class AutoLogAsync(AutoLog):
    async def __call__(self, *args, **kwargs) -> typing.Any:
        res = await self.func(*args, **kwargs)
        return self.handler(res, *args, **kwargs)
