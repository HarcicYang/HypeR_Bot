from Hyper.Manager import Message
from Hyper.ModuleClass import Module, ModuleRegister
from Hyper.Segments import *


@ModuleRegister.register(["message"])
class Ess(Module):
    async def handle(self):
        if len(self.event.message) < 1:
            return
        if isinstance(self.event.message.contents[0], Reply) and ".ess" in str(self.event.message):
            msg_id = (await self.event.message.get())[0]["data"]["id"]
            await self.actions.set_essence_msg(int(msg_id))
            msg = Message(
                [
                    Reply(self.event.message_id),
                    Text("成功")
                ]
            )
            await self.actions.send(group_id=self.event.group_id, message=msg)

