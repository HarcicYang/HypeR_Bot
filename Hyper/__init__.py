from Hyper import Configurator
from Hyper.Utils import Screens

from typing import Coroutine, Union
import asyncio
import importlib
import sys
import os

HYPER_BOT_VERSION = "0.79.1"

listener: "Listener"

Screens.play_startup()
Screens.play_info(HYPER_BOT_VERSION)


def _load_listener() -> None:
    global listener
    listener = importlib.import_module("Hyper.Listener")


def restart() -> None:
    listener.stop()
    os.execv(sys.executable, [sys.executable] + sys.argv)
    # os._exit(1)


class Client:
    def __init__(self):
        self.records = {}

    def subscribe(
            self,
            func: Coroutine,
            event: Union[
                "Events.GroupMessageEvent",
                "Events.PrivateMessageEvent",
                "Events.GroupFileUploadEvent",
                "Events.GroupAdminEvent",
                "Events.GroupMemberDecreaseEvent",
                "Events.GroupMemberIncreaseEvent",
                "Events.GroupMuteEvent",
                "Events.FriendAddEvent",
                "Events.GroupRecallEvent",
                "Events.FriendRecallEvent",
                "Events.NotifyEvent",
                "Events.GroupEssenceEvent",
                "Events.MessageReactionEvent",
                "Events.GroupAddInviteEvent",
                "Events.HyperListenerStartNotify",
                "Events.HyperListenerStopNotify"
            ]
    ) -> None:
        if not self.records.get(event):
            self.records[event] = [func]
        else:
            self.records[event].append(func)

    async def distributor(
            self, message_data: Union["Events.Event", "Events.HyperNotify"], actions: "Listener.Actions"
    ) -> None:
        if type(message_data) in list(self.records.keys()):
            tasks = []
            for i in self.records[type(message_data)]:
                tasks.append(asyncio.create_task(i(message_data, actions)))
            await asyncio.gather(*tasks)
        else:
            return

    def run(self):
        listener.reg(self.distributor)
        if self.records:
            listener.run()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
