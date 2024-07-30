from Hyper.Manager import Message
from Hyper.ModuleClass import Module, ModuleInfo, ModuleRegister
from Hyper.Segments import *


@ModuleRegister.register(["message"])
class Ess(Module):
    @staticmethod
    def info() -> ModuleInfo:
        return ModuleInfo(
            is_hidden=False,
            module_name="Ess",
            desc="设置精华消息",
            helps="引用你要设置的消息，然后在消息框中输入“.ess”，哇！中了！"
        )

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

