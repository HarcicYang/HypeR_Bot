import datetime

import hyperot
from hyperot import events, segments, common
import ModuleClass
from hyperot.events import *


@ModuleClass.ModuleRegister.register(GroupMessageEvent, PrivateMessageEvent)
class TesterCommand(ModuleClass.CommandHandler):
    @ModuleClass.command([".infot"], mapping={1: "usr_code"})
    async def handle_info(self, usr_code: str = "NotMentioned"):
        version = await self.actions.get_version_info()
        name = version.data.app_name
        code = version.data.app_version
        message = ("HypeR Bot v{} - TEST\n"
                   "https://github.com/HarcicYang/HypeR_Bot\n"
                   "\n"
                   "时间：{}\n"
                   "协议库实现：{} {}\n"
                   "code = {}"
                   ).format(
            hyperot.HYPER_BOT_VERSION,
            str(datetime.datetime.now()),
            name,
            code,
            usr_code
        )
        await self.actions.send(group_id=self.event.group_id, user_id=self.event.user_id,
                                message=common.Message(segments.Text(message)))
