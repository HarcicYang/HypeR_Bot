from typing import Any

from hyperot.v2 import Message, Quote, Text
from hyperot.v2.events import MessageReceivedEvent
from typing_extensions import override

import ModuleClass
from ModuleClass import ModuleInfo


@ModuleClass.ModuleRegister.register(MessageReceivedEvent)
class UserTitle(ModuleClass.Module[MessageReceivedEvent]):
    @override
    @staticmethod
    def filter(event: Any, allowed: list[Any]) -> bool:
        return ModuleClass.group_message(event)

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
            gid = int(self.event.scene_id)
            if len(args) == 3:
                await self.api.group(str(gid)).member(str(int(args[1]))).set_title(args[2])
                await self.api.scene(self.event.scene_type, self.event.scene_id).send(
                    Message(Quote(message_id=str(self.event.message_id)), Text(text="成功"))
                )
