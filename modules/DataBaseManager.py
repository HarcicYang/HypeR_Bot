from lib import Manager, Listener, Segements, DataBase

data_set = DataBase.Dataset()


class ModuleClass:
    def __init__(self, actions: Listener.Actions, event: Manager.Event):
        self.actions = actions
        self.event = event

    async def handle(self):
        data_set.load()
        try:
            message = str(self.event.message)
        except AttributeError:
            return None
        if message.startswith(".clear"):
            if "all" not in message:
                item_id = data_set.queue({"user": self.event.user_id})
                data_set.dict_set(item_id, {"user": self.event.user_id})
                self.actions.send(user_id=self.event.user_id, group_id=self.event.group_id,
                                  message=Manager.Message(
                                      [Segements.Reply(self.event.message_id), Segements.Text("成功")]
                                  )
                                  )
            else:
                if self.event.is_owner:
                    data_set.clear()
                    self.actions.send(user_id=self.event.user_id, group_id=self.event.group_id,
                                      message=Manager.Message(
                                          [Segements.Reply(self.event.message_id), Segements.Text("成功")]
                                      )
                                      )
                else:
                    self.actions.send(user_id=self.event.user_id, group_id=self.event.group_id,
                                      message=Manager.Message(
                                          [Segements.Reply(self.event.message_id), Segements.Text("你无权这么做")]
                                      )
                                      )
