from ModuleClass import ModuleInfo
from Hyper.Segments import *
from Hyper.Comm import Message
import ModuleClass
from Hyper.Events import *


@ModuleClass.ModuleRegister.register(GroupMessageEvent)
class UserTitle(ModuleClass.Module):
    @staticmethod
    def info() -> ModuleInfo:
        return ModuleInfo(
            is_hidden=False,
            module_name="UserTitle",
            desc="设置自定义头衔",
            helps="命令：.title <uin> <title>\n\n"
                  "uin：要设置的用户的QQ号，只能在当前聊群设置；\n"
                  "title：要设置的头衔"
        )

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
