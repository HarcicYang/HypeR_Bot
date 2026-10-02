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
            module_name="Reload",
            desc="全量重载所有功能模块",
            helps=".reload - 全量重载 modules/\n.reload status - 查看上次重载结果",
        )

    @override
    @staticmethod
    def filter(event: Event, allowed: list[Any]) -> bool:
        if not isinstance(event, MessageReceivedEvent):
            return False
        if not ModuleClass.is_owner(event):
            return False
        return str(event.message).strip().lower() in (".reload", ".reload status")

    @override
    async def handle(self) -> None:
        text = str(self.event.message).strip().lower()
        if text == ".reload status":
            await self._reply(self._status_text())
            return

        await self._reply("开始全量重载功能模块")
        if not ModuleClass.request_reload():
            await self._reply("已有全量重载任务正在执行")

    async def _reply(self, message: str) -> None:
        await self.api.scene(self.event.scene_type, self.event.scene_id).send(message)

    @staticmethod
    def _status_text() -> str:
        report = ModuleClass.get_last_reload_report()
        if report is None:
            return "尚未执行过全量重载"
        state = "成功" if report.ok else "失败"
        lines = [f"上次全量重载: {state}", f"注册项: {report.module_count}", f"耗时: {report.duration:.2f}s"]
        if report.error:
            lines.append(f"错误: {report.error}")
        if report.errors:
            lines.append("导入错误:")
            lines.extend(f"- {item}" for item in report.errors)
        return "\n".join(lines)
