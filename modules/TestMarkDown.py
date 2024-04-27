from Hyper.Segments import *
from Hyper.Manager import Message
from Hyper import ModuleClass


@ModuleClass.ModuleRegister.register(["message"])
class Test(ModuleClass.Module):
    async def handle(self):
        if str(self.event.message) == ".test":
            content = ("# Markdown"
                       " \n [测试](https://github.com)"
                       " \n `这是一个一个代码块114514`"
                       " \n ```python\nprint('Hello World')```"
                       " \n - 1"
                       " \n - 2")
            forward_result = self.actions.send_forward_msg(
                message=Message(
                    [
                        CustomNode(user_id=f"{self.event.self_id}", nick_name="Hyper Bot", content=Message(
                            [
                                MarkDown(MarkdownContent(content))
                            ]
                        ))
                    ]
                )
            )
            res_id: str = forward_result.data
            message = Message(
                [
                    LongMessage(res_id)
                ]
            )
            self.actions.send(
                message=message,
                group_id=self.event.group_id,
                user_id=self.event.user_id
            )

            row = KeyBoardRow(
                [
                    KeyBoardButton("Test")
                ]
            )

            keyboard = KeyBoard([row])
            self.actions.send(
                user_id=self.event.user_id,
                group_id=self.event.group_id,
                message=Message(
                    [
                        keyboard
                    ]
                )
            )
