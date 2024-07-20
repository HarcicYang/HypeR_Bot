from Hyper.Segments import *
from Hyper.Manager import Message, logger
from Hyper import ModuleClass, Logger
import json
import time


@ModuleClass.ModuleRegister.register(["message"])
class Test(ModuleClass.Module):
    async def handle(self):
        if len(self.event.message) != 0 and isinstance(self.event.message[0], Json):
            text = json.loads((await self.event.message.get())[0]["data"]["data"])
            logger.log(text, level=Logger.levels.DEBUG)
            # with open(f"debug/{int(time.time())}.json", "w", encoding="utf-8") as f:
            #     f.write(str(text))

        if str(self.event.message) == ".test_h":
            content = ("# Markdown"
                       " \n [测试](https://github.com)"
                       " \n `这是一个一个代码块114514`"
                       " \n ```python\nprint('Hello World')```"
                       " \n - 1"
                       " \n - 2")
            forward_result = await self.actions.send_forward_msg(
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
            await self.actions.send(
                message=message,
                group_id=self.event.group_id,
                user_id=self.event.user_id
            )

            row = KeyBoardRow(
                [
                    KeyBoardButton("Ciallo!", data="我。。。我要做主人的新怒！🥵嗯…🥵哈～呃🥵～🥵🥵🥵🥵🥵主人最棒了！再深一点~🥵",
                                   enter=True)
                ]
            )

            keyboard = KeyBoard([row])
            await self.actions.send(
                user_id=self.event.user_id,
                group_id=self.event.group_id,
                message=Message(
                    [
                        keyboard
                    ]
                )
            )

        elif str(self.event.message) == ".test2_h":
            forward_result = await self.actions.send_forward_msg(
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
            await self.actions.send(
                message=message,
                group_id=self.event.group_id,
                user_id=self.event.user_id
            )

        elif str(self.event.message) == ".test3":
            result = await self.actions.get_stranger_info(1449924494)
            print(result.ret_code)
            print(result.data)
            result = await self.actions.get_group_info(group_id=894446744)
            print(result.data)

        elif str(self.event.message) == "Ciallo～(∠・ω< )⌒★":
            row = KeyBoardRow(
                [
                    KeyBoardButton("Ciallo～(∠・ω< )⌒★", data="https://ciallo.cc", button_type=0)
                ]
            )

            keyboard = KeyBoard([row])
            forward_result = await self.actions.send_forward_msg(
                message=Message(
                    [
                        CustomNode(user_id=str(self.event.self_id), nick_name="bot", content=Message([keyboard])
                                   )
                    ]
                )
            )
            res_id: str = forward_result.data
            await self.actions.send(group_id=self.event.group_id, user_id=self.event.user_id,
                                    message=Message([LongMessage(res_id)]))

        elif str(self.event.message) == ".test4":
            await self.actions.send(group_id=self.event.group_id, user_id=self.event.user_id,
                                    message=Message([Dice()]))
