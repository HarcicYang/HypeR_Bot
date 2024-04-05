from Hyper import Manager, ModuleClass, Segments


@ModuleClass.ModuleRegister.register(["message"])
class Module(ModuleClass.Module):
    async def handle(self):
        if self.event.blocked or self.event.servicing:
            return
        try:
            cmds = str(self.event.message)
        except AttributeError:
            return

        if cmds.startswith(f"@{self.event.self_id}"):
            if "先吃饭吧" in cmds:
                self.actions.send(group_id=self.event.group_id,
                                  message=Manager.Message([Segments.Text("好啊好啊，不过，饭还没做好")]))
            elif "先洗澡吧" in cmds:
                self.actions.send(group_id=self.event.group_id,
                                  message=Manager.Message([Segments.Text("好啊好啊，不过，水还没烧好")]))
            elif "嘿嘿我来了" in cmds:
                self.actions.send(group_id=self.event.group_id,
                                  message=Manager.Message([Segments.Text("啊啊啊，什么啊，群友好恐怖呜呜呜")]))
            else:
                custom_row = [
                    Segments.KeyBoardRow(
                        [
                            Segments.KeyBoardButton(text="先吃饭吧", data="先吃饭吧", enter=True),
                            Segments.KeyBoardButton(text="先洗澡吧", data="先洗澡吧", enter=True),
                            Segments.KeyBoardButton(text="先吃我？？", data="嘿嘿我来了小机器人~准备好了吗~~",
                                                    enter=True),
                        ]
                    )
                ]
                message = Manager.Message([Segments.Text("主人会选择哪个套餐呢。。。"), Segments.KeyBoard(custom_row)])
                self.actions.send(group_id=self.event.group_id, user_id=self.event.user_id, message=message)
