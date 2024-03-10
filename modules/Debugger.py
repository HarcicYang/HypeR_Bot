from lib import Manager, ModuleClass, Segments
import uuid
import traceback

registered = []
register = {}


@ModuleClass.ModuleRegister.register(["message"])
class Module(ModuleClass.Module):
    async def handle(self):
        try:
            cmds = str(self.event.message)
        except AttributeError:
            return
        if not self.event.is_owner:
            return

        if cmds.startswith(".debug"):
            cmds = cmds.replace(".debug ", "", 1)
            if cmds.startswith("register"):
                if self.event.group_id is not None:
                    message = Manager.Message(
                        [
                            Segments.Reply(self.event.message_id),
                            Segments.Text("请在私聊中操作")
                        ]
                    )
                    self.actions.send(group_id=self.event.group_id, message=message)
                    return
                if self.event.user_id not in registered:
                    cmds = cmds.replace("register", "", 1)
                    if len(cmds) < 2:
                        verify_code = str(uuid.uuid4())
                        register[self.event.user_id] = verify_code
                        print(f"验证信息： {verify_code}")
                        message = Manager.Message(
                            [
                                Segments.Reply(self.event.message_id),
                                Segments.Text("请前往后台获取验证信息")
                            ]
                        )
                        self.actions.send(
                            user_id=self.event.user_id,
                            message=message
                        )
                        return
                    else:
                        if register[self.event.user_id] in cmds:
                            del register[self.event.user_id]
                            registered.append(self.event.user_id)
                            message = Manager.Message(
                                [
                                    Segments.Reply(self.event.message_id),
                                    Segments.Text("验证成功")
                                ]
                            )
                            self.actions.send(
                                user_id=self.event.user_id,
                                message=message
                            )
                            return
                else:
                    message = Manager.Message(
                        [
                            Segments.Reply(self.event.message_id),
                            Segments.Text("您已验证")
                        ]
                    )
                    self.actions.send(
                        user_id=self.event.user_id,
                        message=message
                    )
                    return

            try:
                if cmds.startswith("exec"):
                    cmds = cmds.replace("exec ", "", 1)
                    exec(cmds)
                    message = Manager.Message(
                        [
                            Segments.Reply(self.event.message_id),
                            Segments.Text("成功")
                        ]
                    )
                    self.actions.send(user_id=self.event.user_id, group_id=self.event.group_id, message=message)

                elif cmds.startswith("eval"):
                    cmds = cmds.replace("eval ", "", 1)
                    result = eval(cmds)
                    message = Manager.Message(
                        [
                            Segments.Reply(self.event.message_id),
                            Segments.Text(result),
                        ]
                    )
                    self.actions.send(user_id=self.event.user_id, group_id=self.event.group_id, message=message)
                    return
            except:
                errors = traceback.format_exc()
                message = Manager.Message(
                    [
                        Segments.Reply(self.event.message_id),
                        Segments.Text("错误:\n\n"),
                        Segments.Text(errors)
                    ]
                )
                self.actions.send(user_id=self.event.user_id, group_id=self.event.group_id, message=message)
                return
