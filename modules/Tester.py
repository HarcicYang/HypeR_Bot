import datetime

import hyperot
from hyperot.v2.events import *
from typing_extensions import override

import ModuleClass


@ModuleClass.ModuleRegister.register(MessageReceivedEvent)
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
        version = await self.api.bot.version()
        name = version.app_name
        code = version.app_version
        message = (
            f"HypeR Bot v{hyperot.HYPER_BOT_VERSION} - TEST\n"
            "https://github.com/HarcicYang/HypeR_Bot\n"
            "\n"
            f"时间：{str(datetime.datetime.now())}\n"
            f"协议库实现：{name} {code}\n"
            f"code = {usr_code}"
        )
        await self.api.scene(self.event.scene_type, self.event.scene_id).send(message)
