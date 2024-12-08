import datetime
import typing
import inspect
import traceback
import sys
from functools import wraps

from Hyper.Utils.Screens import color_txt, rgb


class Levels:
    def __init__(self):
        self.TRACE = color_txt("| Trace    |", rgb(184, 255, 254))
        self.INFO = color_txt("| Info     |", rgb(90, 221, 225))
        self.WARNING = color_txt("| Warning  |", rgb(82, 171, 237))
        self.ERROR = color_txt("| Error    |", rgb(255, 48, 70))
        self.CRITICAL = color_txt("| Critical |", rgb(178, 33, 48))
        self.DEBUG = color_txt("| Debug    |", rgb(93, 227, 144))

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
    running_loggers = {}

    def __init__(self):
        self.log_level = levels.INFO

    @classmethod
    def create(cls, key: str, level: str):
        c = cls()
        c.set_level(level)
        cls.running_loggers[key] = c
        print(key)
        print(c)
        print(cls.running_loggers)
        return c

    @classmethod
    def fetch(cls, key: str):
        print(cls.running_loggers)
        return cls.running_loggers.get(key)

    def set_level(self, level: str):
        if level in levels.level_names:
            self.log_level = levels.level_names[level]
        else:
            self.log("未知的日志等级", levels.ERROR)

        return self

    @staticmethod
    def format_exec():
        exc_type, exc_value, exc_traceback = sys.exc_info()
        formatted = color_txt("\nHypeR Bot Exception traceback: \n\n", rgb(255, 47, 47))
        tb_frames = traceback.extract_tb(exc_traceback)
        FILE = color_txt("File", rgb(85, 173, 238))
        LINE = color_txt("line", rgb(85, 173, 238))
        for frame in tb_frames:
            filename, lineno, func_name, code = frame
            formatted += (
                f"  {FILE} {color_txt(filename, rgb(104, 255, 244))},"
                f" {LINE} {lineno},"
                f" in {color_txt(func_name, rgb(70, 172, 107))}\n"
                f"      {color_txt(code, rgb(255, 255, 255))}\n\n"
            )
        formatted += f"{color_txt(exc_type.__name__, rgb(255, 47, 47))}: "
        formatted += color_txt(exc_value, rgb(255, 255, 255)) + "\n"

        return formatted

    def register_hook(self) -> None:
        def hook(exc_t: typing.Any, exc_v: typing.Any, exc_tb: typing.Any) -> None:
            self.error(self.format_exec())

        sys.excepthook = hook

    def log(self, message: str, level: str = levels.INFO) -> None:
        if levels.level_nums[level] < levels.level_nums[self.log_level]:
            return
        time = color_txt(str(datetime.datetime.now())[:-4], rgb(65, 128, 176))
        if "\n" in message:
            listed = message.split("\n")
            for i in listed:
                if listed.index(i) == 0:
                    listed[0] = "\n"
                    content = f" {time} {level} {color_txt(i, rgb(215, 255, 255))}"
                else:
                    content = " " * 37 + color_txt(i, rgb(215, 255, 255))
                print(content)
        else:
            content = f" {time} {level} {color_txt(message, rgb(215, 255, 255))}"
            print(content)

    def info(self, message: str) -> None:
        self.log(message, levels.INFO)

    def warning(self, message: str) -> None:
        self.log(message, levels.WARNING)

    def error(self, message: str) -> None:
        self.log(message, levels.ERROR)

    def critical(self, message: str) -> None:
        self.log(message, levels.CRITICAL)

    def debug(self, message: str) -> None:
        self.log(message, levels.DEBUG)

    def trace(self, message: str) -> None:
        self.log(message, levels.TRACE)


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
