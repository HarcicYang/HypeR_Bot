import datetime
import platform
from typing import Any

import hyperot
import psutil
from hyperot import common, events, segments
from hyperot.events import *
from typing_extensions import override

import ModuleClass


def bytes_to_human(num: float) -> str:
    """将字节数转换为人类可读的字符串"""
    for unit in ("B", "KB", "MB", "GB", "TB", "PB"):
        if num < 1024.0:
            return f"{num:.1f} {unit}"
        num /= 1024.0
    return f"{num:.1f} EB"


@ModuleClass.ModuleRegister.register(GroupMessageEvent, PrivateMessageEvent)
class Module(ModuleClass.Module[GroupMessageEvent | PrivateMessageEvent]):
    @override
    @staticmethod
    def info() -> ModuleClass.ModuleInfo:
        return ModuleClass.ModuleInfo(
            is_hidden=False,
            module_name="Info",
            desc="显示 Bot 运行信息",
            helps=".info 查看运行信息\n.info ext 查看系统信息",
        )

    @override
    @staticmethod
    def filter(event: events.Event, allowed: list[Any]) -> bool:
        if isinstance(event, HyperNotify) or event.blocked:
            return False

        if not isinstance(event, GroupMessageEvent | PrivateMessageEvent):
            return False

        cmd = str(event.message).strip().lower()
        return cmd in (".info", ".info ext")

    @override
    async def handle(self):
        cmd = str(self.event.message).strip().lower()

        if cmd == ".info ext":
            message = await self._system_message()
        else:
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

    async def _system_message(self) -> str:
        # CPU 使用率（interval 提供短暂的采样以获得准确瞬时值）
        cpu_percent = psutil.cpu_percent(interval=0.1)

        # 内存信息
        vm = psutil.virtual_memory()
        total = bytes_to_human(vm.total)
        used = bytes_to_human(vm.used)
        available = bytes_to_human(vm.available)
        percent = vm.percent

        # 系统名称
        system_name = platform.system()
        release = platform.freedesktop_os_release()
        machine = platform.machine()

        # 系统运行时间
        boot_time = datetime.datetime.fromtimestamp(psutil.boot_time())
        uptime = datetime.datetime.now() - boot_time
        uptime_str = str(uptime).split(".")[0]

        version = await self.actions.get_version_info()
        name = version.data.app_name
        code = version.data.app_version

        return (
            f"HypeR Bot v{hyperot.HYPER_BOT_VERSION}\n"
            "https://github.com/HarcicYang/HypeR_Bot\n"
            "\n"
            f"时间：{str(datetime.datetime.now())}\n"
            f"协议库实现：{name} {code}"
            f"系统名称：{system_name} {release} ({machine})\n"
            f"CPU ：{cpu_percent}%\n"
            "内存 (RAM)：\n"
            f"  已用：{used} / {total} ({percent}%)\n"
            f"  可用：{available}\n"
            f"系统运行时间：{uptime_str}"
        )
