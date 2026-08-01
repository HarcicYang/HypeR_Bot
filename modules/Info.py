import datetime
from typing import Any, override

import hyperot
from hyperot import common, events, segments
from hyperot.events import *

import ModuleClass


@ModuleClass.ModuleRegister.register(GroupMessageEvent, PrivateMessageEvent)
class Module(ModuleClass.Module[GroupMessageEvent | PrivateMessageEvent]):
    @override
    @staticmethod
    def info() -> ModuleClass.ModuleInfo:
        return ModuleClass.ModuleInfo(
            is_hidden=False,
            module_name="Info",
            desc="显示 Bot 运行信息",
            helps="发送 .info 即可",
        )

    @staticmethod
    @override
    @staticmethod
    def filter(event: events.Event, allowed: list[Any]) -> bool:
        if isinstance(event, HyperNotify) or event.blocked:
            return False

        return isinstance(event, (GroupMessageEvent, PrivateMessageEvent)) and str(event.message) == ".info"

    @override
    async def handle(self):
        version = await self.actions.get_version_info()
        name = version.data.app_name
        code = version.data.app_version
        message = (
            f"HypeR Bot v{hyperot.HYPER_BOT_VERSION}\n"
            "https://github.com/HarcicYang/HypeR_Bot\n"
            "\n"
            f"时间：{str(datetime.datetime.now())}\n"
            f"协议库实现：{name} {code}"
        )
        await self.actions.send_msg(
            group_id=self.event.group_id, user_id=self.event.user_id, message=common.Message(segments.Text(message))
        )
