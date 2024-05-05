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
                    KeyBoardButton("这是什么", data="我和校溯都是小南娘。人家已经急不可耐了呢~~", enter=True)
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

        elif str(self.event.message) == ".test2":
            forward_result = self.actions.send_forward_msg(
                message=Message(
                    [
                        CustomNode(user_id="2530894749", nick_name='dext("⁧⁧ ("⁧‭', content=Message(
                            [
                                At("2488529467"),
                                Text("好想🥵，好想被主人宠幸🥵")
                            ]
                        ))
                    ]
                )
            )
            res_id: str = forward_result.data
            message = Message(
                [
                    Forward(res_id)
                ]
            )
            self.actions.send(
                message=message,
                group_id=self.event.group_id,
                user_id=self.event.user_id
            )

        elif str(self.event.message) == ".test3":
            result = self.actions.get_stranger_info(1449924494)
            print(result.ret_code)
            print(result.data)
            result = self.actions.get_group_info(group_id=894446744)
            print(result.data)

        elif str(self.event.message) == "Ciallo～(∠・ω< )⌒★":
            row = KeyBoardRow(
                [
                    KeyBoardButton("Ciallo～(∠・ω< )⌒★", data="https://ciallo.cc", button_type=0)
                ]
            )

            keyboard = KeyBoard([row])
            forward_result = self.actions.send_forward_msg(
                message=Message(
                    [
                        CustomNode(user_id=str(self.event.self_id), nick_name="bot", content=Message([keyboard])
                                   )
                    ]
                )
            )
            res_id: str = forward_result.data
            self.actions.send(group_id=self.event.group_id, user_id=self.event.user_id,
                              message=Message([LongMessage(res_id)]))
