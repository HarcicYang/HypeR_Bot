from typing import Union

from Hyper import Events, Segments, Comm
import ModuleClass
from Hyper.Events import *


@ModuleClass.ModuleRegister.register(GroupMessageEvent, PrivateMessageEvent)
class Module(ModuleClass.Module):
    @staticmethod
    def filter(event: Events.Event, allowed: list) -> bool:
        if isinstance(event, HyperNotify):
            return False

        if isinstance(event, GroupMessageEvent) or isinstance(event, PrivateMessageEvent):
            if event.is_owner and str(event.message).startswith(".alert"):
                return True

        return False

    async def handle(self):
        cmds = str(self.event.message)
        target = cmds.split(" ")[1]
        cmds = cmds.replace(target, "", 1).replace(".alert", "", 1)
        await self.actions.send(group_id=int(target), message=Comm.Message(Segments.Text(cmds)))
