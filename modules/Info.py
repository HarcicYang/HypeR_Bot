from typing import Union
import datetime

import Hyper
from Hyper import Events, Segments
import ModuleClass
from Hyper.Events import *


@ModuleClass.ModuleRegister.register(GroupMessageEvent, PrivateMessageEvent)
class Module(ModuleClass.Module):
    @staticmethod
    def filter(event: Union[*Events.em.events], allowed: list) -> bool:
        if isinstance(event, HyperNotify):
            return False

        if event.blocked:
            return False

        if isinstance(event, GroupMessageEvent) or isinstance(event, PrivateMessageEvent):
            if str(event.message) == ".info":
                return True

        return False

    async def handle(self):
        version = await self.actions.get_version_info()
        name = version.data["app_name"]
        code = version.data["app_version"]
        message = ("HypeR Bot v{}\n"
                   "https://github.com/HarcicYang/HypeR_Bot\n"
                   "\n"
                   "时间：{}\n"
                   "OneBot实现名称：{}"
                   "\n"
                   "OneBot实现版本：{}").format(
            Hyper.HYPER_BOT_VERSION,
            str(datetime.datetime.now()),
            name,
            code
        )
        await self.actions.send(group_id=self.event.group_id, user_id=self.event.user_id,
                                message=Manager.Message(Segments.Text(message)))
