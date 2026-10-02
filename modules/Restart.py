from __future__ import annotations

from typing import Any

from hyperot.v2.events import Event, MessageReceivedEvent
from typing_extensions import override

import ModuleClass


@ModuleClass.ModuleRegister.register(MessageReceivedEvent)
class Module(ModuleClass.Module[MessageReceivedEvent]):
    @override
    @staticmethod
    def info() -> ModuleClass.ModuleInfo:
        return ModuleClass.ModuleInfo(
            is_hidden=False,
            module_name="Restart",
            desc="重启 Bot 进程",
            helps=".restart - 重启 Bot 进程",
        )

    @override
    @staticmethod
    def filter(event: Event, allowed: list[Any]) -> bool:
        if not isinstance(event, MessageReceivedEvent):
            return False
        if not ModuleClass.is_owner(event):
            return False
        return str(event.message).strip().lower() == ".restart"

    @override
    async def handle(self) -> None:
        await self.api.scene(self.event.scene_type, self.event.scene_id).send("准备重启 Bot")
        if not ModuleClass.request_restart():
            await self.api.scene(self.event.scene_type, self.event.scene_id).send("重启请求未能提交")
