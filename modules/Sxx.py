from random import randint
from typing import Any

from hyperot.v2 import Mention, Message, Text
from hyperot.v2.events import *
from typing_extensions import override

from ModuleClass import Module, ModuleInfo, ModuleRegister, group_message

user_hist: dict[int, int] = {}


@ModuleRegister.register(MessageReceivedEvent)
class Sxx(Module[MessageReceivedEvent]):
    @override
    @staticmethod
    def filter(event: Any, allowed: list[Any]) -> bool:
        return group_message(event)

    @override
    @staticmethod
    def info() -> ModuleInfo:
        return ModuleInfo(is_hidden=False, module_name="Sxx", desc="自助被强碱", helps="发送“透我”即可")

    @override
    async def handle(self):
        if self.event.user_id is None:
            return
        uid = int(self.event.user_id)
        gid = int(self.event.scene_id)
        if "透我" in str(self.event.message):
            flag1 = True
            flag2 = True
            time = 0
            while flag1 and flag2:
                if flag2:
                    if self.event.user_id in list(user_hist.keys()):
                        c: float = user_hist[uid] * 0.1
                    else:
                        user_hist[uid] = 0
                        c: float = 0.0
                    time = int(randint(0, round(100 - c)) * 5.2)
                else:
                    flag2 = False
                if time > 200:
                    continue

                flag1 = False
                continue

            if time < 20:
                msg = Message(Mention(user_id=str(uid)), Text(text="你被透了，但是你似乎很会啊，居然还能保持清醒"))
            elif 20 <= time < 60:
                msg = Message(Mention(user_id=str(uid)), Text(text="你被透了，但是你好像经验丰富，快醒来了呢"))
            elif 60 <= time < 180:
                msg = Message(Mention(user_id=str(uid)), Text(text="你被透了，头昏眼花"))
            else:
                msg = Message(Mention(user_id=str(uid)), Text(text="才透了几下就成这样了，行不行啊小泡芙，又菜又爱玩"))

            await self.api.group(str(gid)).member(str(uid)).mute(time)
            await self.api.group(str(gid)).send(msg)
            user_hist[uid] += 1
