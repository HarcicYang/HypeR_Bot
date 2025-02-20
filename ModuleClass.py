import inspect

from hyperot import events, listener, hyperogger, configurator
from hyperot.utils.hypetyping import Any, Union
from hyperot.utils.typextensions import String

import gc
import asyncio
import importlib
import dataclasses


config: configurator.BotConfig = configurator.BotConfig.get("hyper-bot")
logger = hyperogger.Logger()
logger.set_level(config.log_level)


@dataclasses.dataclass
class ModuleInfo:
    is_hidden: bool = True
    module_name: str = "None"
    author: str = "None"
    version: str = "0.0"
    desc: str = "None"
    helps: str = "None"


class Module:
    config = config

    def __init__(
            self,
            actions: listener.Actions,
            event: Union[
                events.GroupMessageEvent,
                events.PrivateMessageEvent,
                events.GroupFileUploadEvent,
                events.GroupAdminEvent,
                events.GroupMemberDecreaseEvent,
                events.GroupMemberIncreaseEvent,
                events.GroupMuteEvent,
                events.FriendAddEvent,
                events.GroupRecallEvent,
                events.FriendRecallEvent,
                events.NotifyEvent,
                events.GroupEssenceEvent,
                events.MessageReactionEvent,
                events.GroupAddInviteEvent,
                events.HyperListenerStartNotify,
                events.HyperListenerStopNotify
            ]
    ):
        self.actions: listener.Actions = actions
        self.event: Union[
                events.GroupMessageEvent,
                events.PrivateMessageEvent,
                events.GroupFileUploadEvent,
                events.GroupAdminEvent,
                events.GroupMemberDecreaseEvent,
                events.GroupMemberIncreaseEvent,
                events.GroupMuteEvent,
                events.FriendAddEvent,
                events.GroupRecallEvent,
                events.FriendRecallEvent,
                events.NotifyEvent,
                events.GroupEssenceEvent,
                events.MessageReactionEvent,
                events.GroupAddInviteEvent,
                events.HyperListenerStartNotify,
                events.HyperListenerStopNotify
            ] = event

    async def handle(self):
        pass

    @staticmethod
    def info() -> ModuleInfo:
        return ModuleInfo()

    @staticmethod
    def filter(event: events.Event, allowed: list) -> bool:
        for i in allowed:
            if isinstance(event, i):
                return True

        return False


@dataclasses.dataclass
class CommandPara:
    name: str
    annotation: type = str
    default: annotation = ""


def para_empty(obj: Any) -> bool:
    return obj is inspect.Parameter.empty


class FieldNotEqualException(Exception):
    pass


class CommandRegistration:
    def __init__(self, chain: list[str], mapping: dict[Union[int, str], str], function: callable):
        self.chain = chain
        self.mapping = mapping
        self.function = function
        signature = inspect.signature(self.function).parameters
        self.signature: list[CommandPara] = []
        for i, j in signature.items():
            self.signature.append(CommandPara(i, j.annotation, j.default, ))

    async def __call__(self, sub_self: "CommandHandler", cmds: list) -> Any:
        return await self.function(**self.gen_args(cmds, sub_self))

    @property
    def length_chain(self) -> int:
        return len(self.chain)

    def if_equal(self, cmd: list) -> bool:
        flags = [False for _ in self.chain]
        try:
            for i in range(len(self.chain)):
                if self.chain[i] == cmd[i]:
                    flags[i] = True
            if all(flags):
                return True
        except IndexError:
            return False

        return False

    def gen_args(self, cmd: list, sub_self: "CommandHandler") -> dict:
        new = {"self": sub_self}
        for i in self.mapping:
            if isinstance(i, int):
                try:
                    new[self.mapping[i]] = cmd[i]
                except IndexError:
                    for j in self.signature:
                        if j.name == self.mapping[i] and not para_empty(j.default):
                            new[self.mapping[i]] = j.default
                            break
                    else:
                        raise FieldNotEqualException(f"index={i}: 缺少参数")
            elif isinstance(i, str):
                have = False
                for j in cmd:
                    if isinstance(j, dict) and j.get(i):
                        have = True
                if not have:
                    for k in self.signature:
                        if k.name == self.mapping[i] and not para_empty(k.default):
                            new[self.mapping[i]] = k.default
                            continue
                    else:
                        raise FieldNotEqualException(f"缺少参数 {i}")

        return new


def command(chain: list[str], mapping: dict[Union[int, str], str]):
    def decorator(func) -> CommandRegistration:
        return CommandRegistration(chain, mapping, func)

    return decorator


class CommandHandler(Module):
    handlers: list[CommandRegistration] = []

    async def handle(self):
        cmds = String(self.event.message).cmdl_parse()
        for i in self.handlers:
            if i.if_equal(cmds):
                try:
                    await i(self, cmds)
                except Exception as e:
                    await self.actions.send(
                        group_id=self.event.group_id,
                        user_id=self.event.user_id,
                        message=repr(e)
                    )

    def __init_subclass__(cls, **kwargs):
        cls.handlers = [].copy()
        for i in inspect.getmembers(cls):
            if not isinstance(i[1], CommandRegistration):
                continue
            else:
                cls.handlers.append(i[1])
        return cls


class InnerHandler:
    def __init__(self, module: Module, allowed: list):
        self.module = module
        self.allowed = allowed


register_modules: list[InnerHandler] = []


class ModuleRegister:
    @staticmethod
    def register(*args):
        def decorator(cls):
            if len(args) < 1:
                allowed = [events.Event]
            else:
                allowed = list(args)

            def init(self, actions: listener.Actions, event: events.Event):
                self.actions = actions
                self.event = event

            cls.__init__ = init

            register_modules.append(InnerHandler(cls, allowed))

            return cls

        return decorator

    @staticmethod
    def get_registered() -> list:
        return register_modules


imported = None


def load() -> None:
    global imported, register_modules
    register_modules = []
    if imported is not None:
        imported.load()
        imported = importlib.reload(imported)
    else:
        imported = importlib.import_module("modules")


class TaskCxt:
    def __init__(self):
        self.tasks = []

    def add(self, task: asyncio.Task) -> None:
        self.tasks.append(task)

    async def wait(self) -> None:
        await asyncio.gather(*self.tasks)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.wait()
        gc.collect()
