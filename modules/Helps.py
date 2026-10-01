from collections.abc import Callable

from hyperot.v2 import Message, Text
from hyperot.v2.events import *
from typing_extensions import override

from ModuleClass import InnerHandler, Module, ModuleInfo, ModuleRegister


def searcher(checker: Callable[[InnerHandler], bool], iter_obj: list[InnerHandler]) -> list[InnerHandler]:
    return list(filter(checker, iter_obj))


@ModuleRegister.register(MessageReceivedEvent)
class Helper(Module[MessageReceivedEvent]):
    @override
    @staticmethod
    def info() -> ModuleInfo:
        return ModuleInfo(
            is_hidden=True,
            module_name="Helper",
            desc="显示机器人帮助信息",
            helps="命令：\n.help - 列出所有模块\n.help <模块名> - 显示某个模块的详细帮助",
        )

    @override
    async def handle(self):
        if str(self.event.message).startswith(".help"):
            try:
                name = str(self.event.message).split(" ", maxsplit=1)[1]
            except IndexError:
                name = None

            if name is None:
                help_info = "--- HypeR Bot 帮助 ---\n"
                for i in ModuleRegister.get_registered():
                    m_info = i.module.info()
                    if m_info.is_hidden:
                        continue
                    help_info += f"\n{m_info.module_name} - {m_info.desc}"
                help_info += "\n\n使用命令“.help <module name>”获得更多信息\n\nHypeR Bot操作手册：https://harcicyang.github.io/hyper-bot/usage/qq_usage/"

            else:

                def check(x: InnerHandler):
                    return x.module.info().module_name == name

                res = searcher(check, ModuleRegister.get_registered())
                help_info = f"--- {name} 帮助 ---\n{res[0].module.info().helps}" if len(res) != 0 else "未找到这个模块"

            await self.api.scene(self.event.scene_type, self.event.scene_id).send(Message(Text(text=help_info)))
