from datetime import datetime, time
from typing import Any

import hyperot
from hyperot import common, events, segments
from hyperot.events import *
from typing_extensions import override

import ModuleClass


@ModuleClass.ModuleRegister.register(GroupMessageEvent)
class Module(ModuleClass.Module[GroupMessageEvent]):
    @override
    @staticmethod
    def info() -> ModuleClass.ModuleInfo:
        return ModuleClass.ModuleInfo(
            is_hidden=False,
            module_name="DSMon",
            desc="展示 DeepSeek 定价时段",
            helps="发送“梁文”或 .ds 即可",
        )

    def is_peak(self) -> bool:
        return time(9, 0) <= datetime.now().time() <= time(12, 0) or time(14, 0) <= datetime.now().time() <= time(18, 0)

    def build_msg(self) -> str:
        return f"现在是梁文{'峰，小心钱包' if self.is_peak() else '谷，放心蹬'}"

    @override
    async def handle(self):
        if "梁文" in str(self.event.message).replace("梁文锋", "") or str(self.event.message) == ".ds":
            await self.actions.send_msg(
                user_id=self.event.user_id,
                group_id=self.event.group_id,
                message=f"现在是梁文{'峰，小心钱包' if self.is_peak() else '谷，放心蹬'}"
            )
