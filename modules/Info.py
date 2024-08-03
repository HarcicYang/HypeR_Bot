from Hyper import Manager, ModuleClass, Segments
from Hyper.Events import *
import datetime


@ModuleClass.ModuleRegister.register(GroupMessageEvent, PrivateMessageEvent)
class Module(ModuleClass.Module):
    async def handle(self):
        if self.event.blocked or self.event.servicing:
            return
        try:
            cmd = str(self.event.message)
        except AttributeError:
            return None

        if cmd == ".info":
            version = await self.actions.get_version_info()
            name = version.data["app_name"]
            code = version.data["app_version"]
            message = ("HypeR Bot v0.7\n"
                       "https://github.com/HarcicYang/HypeR_Bot\n"
                       "\n"
                       "时间：{}\n"
                       "OneBot实现名称：{}"
                       "\n"
                       "OneBot实现版本：{}").format(
                str(datetime.datetime.now()),
                name,
                code
            )
            await self.actions.send(group_id=self.event.group_id, user_id=self.event.user_id,
                                    message=Manager.Message([Segments.Text(message)]))
