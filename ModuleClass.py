from Hyper import Events, Listener, Logger, Configurator

import gc
import asyncio
import importlib
from typing import Union
import dataclasses

config = Configurator.cm.get_cfg()
logger = Logger.Logger()
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
    def __init__(
            self,
            actions: Listener.Actions,
            event: Union[
                Events.GroupMessageEvent,
                Events.PrivateMessageEvent,
                Events.GroupFileUploadEvent,
                Events.GroupAdminEvent,
                Events.GroupMemberDecreaseEvent,
                Events.GroupMemberIncreaseEvent,
                Events.GroupMuteEvent,
                Events.FriendAddEvent,
                Events.GroupRecallEvent,
                Events.FriendRecallEvent,
                Events.NotifyEvent,
                Events.GroupEssenceEvent,
                Events.MessageReactionEvent,
                Events.GroupAddInviteEvent,
                Events.HyperListenerStartNotify,
                Events.HyperListenerStopNotify
            ]
    ):
        self.actions = actions
        self.event = event

    async def handle(self):
        pass

    @staticmethod
    def info() -> ModuleInfo:
        return ModuleInfo()

    @staticmethod
    def filter(
            event: Union[
                Events.GroupMessageEvent,
                Events.PrivateMessageEvent,
                Events.GroupFileUploadEvent,
                Events.GroupAdminEvent,
                Events.GroupMemberDecreaseEvent,
                Events.GroupMemberIncreaseEvent,
                Events.GroupMuteEvent,
                Events.FriendAddEvent,
                Events.GroupRecallEvent,
                Events.FriendRecallEvent,
                Events.NotifyEvent,
                Events.GroupEssenceEvent,
                Events.MessageReactionEvent,
                Events.GroupAddInviteEvent,
                Events.HyperListenerStartNotify,
                Events.HyperListenerStopNotify
            ],
            allowed: list
    ) -> bool:
        for i in allowed:
            if isinstance(event, i):
                return True

        return False


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
                allowed = [Events.Event]
            else:
                allowed = list(args)

            def init(self, actions: Listener.Actions, event: Events.Event):
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
