from lib import Manager, Listener, Segments


class ModuleClass:
    def __init__(self, actions: Listener.Actions, event: Manager.Event):
        self.actions = actions
        self.event = event

    async def handle(self):
        try:
            cmds = str(self.event.message)
        except AttributeError:
            return

        if cmds.startswith(".alert"):
            target = cmds.split(" ")[1]
            cmds = cmds.replace(target, "", 1).replace(".alert", "", 1)
            self.actions.send(group_id=int(target), message=Manager.Message(
                [Segments.Text(cmds)]
            ))
