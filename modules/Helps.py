from Hyper.Manager import Message
from Hyper.Segments import *
from Hyper.ModuleClass import Module, ModuleInfo, ModuleRegister, InnerHandler
from Hyper.Events import *


def searcher(checker, iter_obj: list) -> list[InnerHandler]:
    return list(filter(checker, iter_obj))


@ModuleRegister.register(GroupMessageEvent, PrivateMessageEvent)
class Helper(Module):
    async def handle(self):
        if str(self.event.message).startswith(".help"):
            try:
                name = str(self.event.message).split(" ")[1]
            except IndexError:
                name = None

            if name is None:
                help_info = "--- HypeR Bot 帮助 ---\n"
                for i in ModuleRegister.get_registered():
                    m_info = i.module.info()
                    if m_info.is_hidden:
                        continue
                    help_info += f"\n{m_info.module_name} - {m_info.desc}"
                help_info += "\n\n使用命令“.help <module name>”获得更多信息"

            else:
                def check(x: InnerHandler):
                    if x.module.info().module_name == name:
                        return True
                    return False
                res = searcher(check, ModuleRegister.get_registered())
                if len(res) == 0:
                    help_info = "未找到这个模块"
                else:
                    help_info = (f"--- {name} 帮助 ---\n"
                                 f"{res[0].module.info().helps}")

            await self.actions.send(
                group_id=self.event.group_id,
                user_id=self.event.user_id,
                message=Message(
                    [
                        Text(help_info)
                    ]
                ),
            )
