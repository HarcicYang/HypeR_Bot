import datetime
from typing import override

import hyperot
from hyperot import common, segments
from hyperot.events import *

import ModuleClass


@ModuleClass.ModuleRegister.register(GroupMessageEvent, PrivateMessageEvent)
class TesterCommand(ModuleClass.CommandHandler):
    @staticmethod
    @override
    @staticmethod
    def info() -> ModuleClass.ModuleInfo:
        return ModuleClass.ModuleInfo(
            is_hidden=True,
            module_name="Tester",
            desc="开发者测试模块",
            helps="命令：.infot <code> - 打印运行信息及自定义代码",
        )

    @ModuleClass.command([".infot"], mapping={1: "usr_code"})
    async def handle_info(self, usr_code: str = "NotMentioned"):
        version = await self.actions.get_version_info()
        name = version.data.app_name
        code = version.data.app_version
        message = (
            f"HypeR Bot v{hyperot.HYPER_BOT_VERSION} - TEST\n"
            "https://github.com/HarcicYang/HypeR_Bot\n"
            "\n"
            f"时间：{str(datetime.datetime.now())}\n"
            f"协议库实现：{name} {code}\n"
            f"code = {usr_code}"
        )
        await self.actions.send_msg(
            group_id=self.event.group_id, user_id=self.event.user_id, message=common.Message(segments.Text(message))
        )
