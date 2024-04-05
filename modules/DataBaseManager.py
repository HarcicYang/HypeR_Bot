from Hyper import Manager, ModuleClass, Segments, DataBase

data_set = DataBase.Dataset()


@ModuleClass.ModuleRegister.register(["message"])
class Module(ModuleClass.Module):
    async def handle(self):
        if self.event.blocked:
            return
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
                                      [Segments.Reply(self.event.message_id), Segments.Text("成功")]
                                  )
                                  )
            else:
                if self.event.is_owner:
                    data_set.clear()
                    self.actions.send(user_id=self.event.user_id, group_id=self.event.group_id,
                                      message=Manager.Message(
                                          [Segments.Reply(self.event.message_id), Segments.Text("成功")]
                                      )
                                      )
                else:
                    self.actions.send(user_id=self.event.user_id, group_id=self.event.group_id,
                                      message=Manager.Message(
                                          [Segments.Reply(self.event.message_id), Segments.Text("你无权这么做")]
                                      )
                                      )
