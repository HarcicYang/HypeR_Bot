from lib import Manager, Listener, Segments
import datetime


class ModuleClass:
    def __init__(self, actions: Listener.Actions, event: Manager.Event):
        self.actions = actions
        self.event = event

    async def handle(self):
        try:
            cmd = str(self.event.message)
        except AttributeError:
            return None

        if cmd == ".info":
            version = self.actions.get_version_info()
            name = version.data["app_name"]
            code = version.data["app_version"]
            message = ("HypeR Bot v0.2\n"
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
            self.actions.send(group_id=self.event.group_id, message=Manager.Message([Segments.Text(message)]))
