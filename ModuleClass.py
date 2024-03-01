from lib import Manager, Listener, Segments


class ModuleClass:
    def __init__(self, actions: Listener.Actions, event: Manager.Event):
        self.actions = actions
        self.event = event

    async def handle(self):
        message = Manager.Message([Segements.Text("Hello World" + " " + str(self.event.message))])
        self.actions.send(user_id=self.event.user_id, group_id=self.event.group_id, message=message)