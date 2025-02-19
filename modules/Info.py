import datetime

import hyperot
from hyperot import events, segments, common
import ModuleClass
from hyperot.events import *


@ModuleClass.ModuleRegister.register(GroupMessageEvent, PrivateMessageEvent)
class Module(ModuleClass.Module):
    @staticmethod
    def filter(event: events.Event, allowed: list) -> bool:
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
        name = version.data.app_name
        code = version.data.app_version
        message = ("HypeR Bot v{}\n"
                   "https://github.com/HarcicYang/HypeR_Bot\n"
                   "\n"
                   "时间：{}\n"
                   "协议库实现：{} {}").format(
            hyperot.HYPER_BOT_VERSION,
            str(datetime.datetime.now()),
            name,
            code
        )
        await self.actions.send(group_id=self.event.group_id, user_id=self.event.user_id,
                                message=common.Message(segments.Text(message)))
