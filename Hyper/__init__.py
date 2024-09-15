from Hyper.Listener import stop, reg, run, Actions
from Events import *

from typing import Coroutine, Union
import sys
import os

HYPER_BOT_VERSION = "0.78.5"


def restart() -> None:
    stop()
    os.execv(sys.executable, [sys.executable] + sys.argv)
    # os._exit(1)


class Client:
    def __init__(self):
        self.records = {}
        reg(self.distributor)

    def subscribe(
            self,
            func: Coroutine,
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
    ) -> None:
        self.records[event] = func

    async def distributor(self, message_data: Union[Event, HyperNotify], actions: Actions) -> None:
        if type(message_data) in list(self.records.keys()):
            await self.records[actions](message_data, actions)
        else:
            return

    def run(self):
        if self.records:
            run()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass
