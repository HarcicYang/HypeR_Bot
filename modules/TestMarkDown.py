import json
import time

from hyperot.common import Message, Ret
from hyperot.events import *
from hyperot.segments import *
from hyperot.segments import Reply
from hyperot.utils.ark_sign_helper import Card, get_pic
from typing_extensions import override

import ModuleClass


@ModuleClass.ModuleRegister.register(MessageEvent)
class Test(ModuleClass.Module[MessageEvent]):
    @override
    @staticmethod
    def info() -> ModuleClass.ModuleInfo:
        return ModuleClass.ModuleInfo(
            is_hidden=True,
            module_name="TestMarkDown",
            desc="Markdown/消息类型测试模块",
            helps="主人专用测试模块，测试各种消息类型（Markdown、键盘、转发节点、Ark 卡片等）",
        )

    @override
    async def handle(self):
        if len(self.event.message) != 0:
            for i in self.event.message:
                if isinstance(i, Forward):
                    nodes = await self.actions.forward_solve(self.event.message)
                    for j in nodes:
                        print(f"{j.nickname}({j.user_id}) {j.content}")
                    break
            # with open(f"debug/{int(time.time())}.json", "w", encoding="utf-8") as f:
            #     f.write(str(text))

        if not self.event.is_owner:
            return

        if str(self.event.message) == ".test_h":
            # return
            # content = ("# Markdown"
            #            " \n [测试](https://github.com)"
            #            " \n `这是一个一个代码块114514`"
            #            " \n ```python\nprint('Hello World')```"
            #            " \n - 1"
            #            " \n - 2")
            # forward_result = await self.actions.send_forward_msg(
            #     message=Message(
            #         [
            #             CustomNode(user_id=f"{self.event.self_id}", nick_name="Hyper Bot", content=Message(
            #                 [
            #                     MarkDown(MarkdownContent(content))
            #                 ]
            #             ))
            #         ]
            #     )
            # )
            # res_id: str = forward_result.data
            # message = Message(
            #     CustomNode(
            #         user_id=f"{self.event.self_id}",
            #         nick_name="Hyper Bot",
            #         content=Message(LongMessage(res_id))
            #     )
            # )
            # await self.actions.send_msg(
            #     message=message,
            #     group_id=self.event.group_id,
            #     user_id=self.event.user_id
            # )

            row = KeyBoardRow(
                [
                    KeyBoardButton(
                        "Ciallo!",
                        data="我。。。我要做主人的新怒！🥵嗯…🥵哈～呃🥵～🥵🥵🥵🥵🥵主人最棒了！再深一点~🥵",
                        enter=True,
                    )
                ]
            )

            keyboard = KeyBoard([row])
            await self.actions.send_msg(
                user_id=self.event.user_id, group_id=self.event.group_id, message=Message([keyboard])
            )

        elif str(self.event.message) == ".test2_h":
            await self.actions.send_msg(
                message=Message(
                    [
                        Forward(
                            content=[
                                CustomNode(
                                    user_id="2530894749",
                                    nickname='dext("⁧⁧ ("⁧‭',
                                    content=Message([At("2488529467"), Text("好想🥵，好想被主人宠幸🥵")]),
                                ).to_json()
                            ]
                        )
                    ]
                ),
                group_id=self.event.group_id,
                user_id=self.event.user_id,
            )
            # res_id: str = forward_result.data.res_id
            # print(forward_result.raw)
            # message = Message(
            #     [
            #         Forward(res_id)
            #     ]
            # )
            # await self.actions.send_msg(
            #     message=message,
            #     group_id=self.event.group_id,
            #     user_id=self.event.user_id
            # )

        elif str(self.event.message) == ".test3":
            result = await self.actions.get_stranger_info(2488529467)
            print(result.ret_code)
            await self.actions.send_msg(
                Message(Reply(self.event.message_id), Text(json.dumps(result.data.raw))),
                group_id=self.event.group_id,
                user_id=self.event.user_id,
            )

        elif str(self.event.message) == "Ciallo～(∠・ω< )⌒★":
            row = KeyBoardRow([KeyBoardButton("Ciallo～(∠・ω< )⌒★", data="https://ciallo.cc", button_type=0)])

            keyboard = KeyBoard([row])
            forward_result = await self.actions.send_forward_msg(
                message=Message(
                    [CustomNode(user_id=str(self.event.self_id), nickname="bot", content=Message([keyboard]))]
                )
            )
            res_id: str = forward_result.data.res_id
            await self.actions.send_msg(
                group_id=self.event.group_id, user_id=self.event.user_id, message=Message([LongMessage(res_id)])
            )
        elif str(self.event.message) == "我们的小溯":
            row = KeyBoardRow([KeyBoardButton("小溯溯真棒", data="👍", enter=True, style=0)])

            keyboard = KeyBoard([row])
            forward_result = await self.actions.send_forward_msg(
                message=Message(
                    [CustomNode(user_id=str(self.event.self_id), nickname="bot", content=Message([keyboard]))]
                )
            )
            res_id: str = forward_result.data.res_id
            await self.actions.send_msg(
                group_id=self.event.group_id, user_id=self.event.user_id, message=Message([LongMessage(res_id)])
            )

        elif str(self.event.message) == ".test4":
            await self.actions.send_msg(
                group_id=self.event.group_id, user_id=self.event.user_id, message=Message([Dice()])
            )

        elif str(self.event.message) == ".test5":
            message = Message(
                [
                    Music(
                        type="custom",
                        url="https://harcicyang.github.io/schools",
                        audio="https://harcicyang.github.io/ctrl.m4a",
                        title="Test",
                    )
                ]
            )
            await self.actions.send_msg(group_id=self.event.group_id, message=message)

        elif str(self.event.message) == ".test6":
            echo = await self.actions.custom.get_cookies(domain="qun.qq.com")
            rsp = await Ret.fetch(echo)
            print(rsp.data)

        elif str(self.event.message) == ".test7":
            ark = Card(
                title="",
                desc="",
                jump_url="",
                music_url="",
                source_icon="https://p.qlogo.cn/homework/0/hw_h_owx0c2pifdccko66c04ddfbdc62/0",
                tag="",
                preview="https://p.qlogo.cn/homework/0/hw_h_owx0c2pifdccko66c04ddfbdc62/0",
            )
            card = Json(await ark.get_sig(self.actions, self.event.self_id))
            await self.actions.send_msg(group_id=self.event.group_id, user_id=self.event.user_id, message=Message(card))

        elif str(self.event.message) == ".test8":
            c = {
                "app": "com.tencent.tdoc.qqpush",
                "config": {"ctime": int(time.time()), "token": ""},
                "meta": {
                    "contact": {
                        "avatar": await get_pic(self.actions, self.event.self_id, "./temps/ra.jpg"),
                        "contact": "你好！这里是 Rick Astley 唯一的官方QQ账号。",
                        "jumpUrl": "https://bilibili.com/video/BV1GJ411x7h7/",
                        "nickname": "Rick Astley",
                        "tag": "推荐用户",
                        "tagIcon": "https://p.qlogo.cn/gh/367798007/367798007/100",
                    }
                },
                "prompt": "推荐用户",
                "ver": "",
                "view": "contact",
            }
            ark = Card.any(c)
            card = Json(await ark.get_sig(self.actions, self.event.self_id))
            await self.actions.send_msg(group_id=self.event.group_id, user_id=self.event.user_id, message=Message(card))

        elif str(self.event.message) == ".test9":
            msg = Message(
                StreamTest("ni shuo ni bu xiang zai zhe li wo ye bu xiang zai zhe li"),
                StreamTest("wo ye bu xiang zai zhe li"),
                StreamTest("dan tian hei de tai kuai xiang zou zao jiu lai bu ji"),
                StreamTest("oh wo ai ni"),
                StreamTest("ke xi guan xi bian cheng mei guan xi"),
                StreamTest("wen ti shi mei wen ti"),
                StreamTest("yu shi wo men ji xu"),
            )
            # msg = Message(
            #     StreamTest("ni shuo ni bu xiang zai zhe li wo ye bu xiang zai zhe li")
            # )
            await self.actions.send_msg(group_id=self.event.group_id, user_id=self.event.user_id, message=msg)
