from hyperot.common import Message
from hyperot.events import *
from hyperot.segments import *
from typing_extensions import override

import ModuleClass
from ModuleClass import ModuleInfo


@ModuleClass.ModuleRegister.register(GroupMessageEvent)
class UserTitle(ModuleClass.Module[GroupMessageEvent]):
    @override
    @staticmethod
    def info() -> ModuleInfo:
        return ModuleInfo(
            is_hidden=False,
            module_name="UserTitle",
            desc="设置自定义头衔",
            helps="命令：.title <uin> <title>\n\nuin：要设置的用户的QQ号，只能在当前聊群设置；\ntitle：要设置的头衔",
        )

    @override
    async def handle(self):
        if str(self.event.message).startswith(".title"):
            args = str(self.event.message).split(" ")
            if len(args) == 3 and self.event.group_id is not None:
                await self.actions.set_group_special_title(
                    group_id=self.event.group_id, title=args[2], user_id=int(args[1])
                )
                await self.actions.send_msg(
                    group_id=self.event.group_id,
                    user_id=self.event.user_id,
                    message=Message([Reply(self.event.message_id), Text("成功")]),
                )
