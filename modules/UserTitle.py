from Hyper.Segments import *
from Hyper.Manager import Message
from Hyper import ModuleClass


@ModuleClass.ModuleRegister.register(["message"])
class UserTitle(ModuleClass.Module):
    async def handle(self):
        if str(self.event.message).startswith(".title"):
            args = str(self.event.message).split(" ")
            if len(args) == 3:
                await self.actions.set_group_special_title(group_id=int(self.event.group_id), title=args[2],
                                                           user_id=int(args[1]))
                await self.actions.send(group_id=self.event.group_id, user_id=self.event.user_id, message=Message(
                    [
                        Reply(self.event.message_id),
                        Text("成功")
                    ]
                ))
