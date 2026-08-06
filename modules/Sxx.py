from random import randint

from hyperot.common import Message
from hyperot.events import *
from hyperot.segments import *
from typing_extensions import override

from ModuleClass import Module, ModuleInfo, ModuleRegister

user_hist: dict[int, int] = {}


@ModuleRegister.register(GroupMessageEvent)
class Sxx(Module[GroupMessageEvent]):
    @override
    @staticmethod
    def info() -> ModuleInfo:
        return ModuleInfo(is_hidden=False, module_name="Sxx", desc="自助被强碱", helps="发送“透我”即可")

    @override
    async def handle(self):
        if self.event.user_id is None or self.event.group_id is None:
            return
        if "透我" in str(self.event.message):
            flag1 = True
            flag2 = True
            time = 0
            while flag1 and flag2:
                if flag2:
                    if self.event.user_id in list(user_hist.keys()):
                        c: float = user_hist[self.event.user_id] * 0.1
                    else:
                        user_hist[self.event.user_id] = 0
                        c: float = 0.0
                    time = int(randint(0, round(100 - c)) * 5.2)
                else:
                    flag2 = False
                if time > 200:
                    continue

                flag1 = False
                continue

            if time < 20:
                msg = Message([At(str(self.event.user_id)), Text("你被透了，但是你似乎很会啊，居然还能保持清醒")])
            elif 20 <= time < 60:
                msg = Message([At(str(self.event.user_id)), Text("你被透了，但是你好像经验丰富，快醒来了呢")])
            elif 60 <= time < 180:
                msg = Message([At(str(self.event.user_id)), Text("你被透了，头昏眼花")])
            else:
                msg = Message([At(str(self.event.user_id)), Text("才透了几下就成这样了，行不行啊小泡芙，又菜又爱玩")])

            await self.actions.set_group_ban(self.event.group_id, self.event.user_id, time)
            await self.actions.send_msg(group_id=self.event.group_id, message=msg)
            user_hist[self.event.user_id] += 1
