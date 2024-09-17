from Hyper.Comm import Message
from Hyper.Segments import Text
from Hyper.Events import MessageEvent
from ModuleClass import ModuleRegister, Module

import httpx


@ModuleRegister.register(MessageEvent)
class Quote(Module):
    async def handle(self):
        if str(self.event.message) == "一言":
            response = httpx.get("https://international.v1.hitokoto.cn/")
            try:
                txt = f"{response.json()['hitokoto']} —— {response.json()['from_who']}, {response.json()['from']}"
            except:
                txt = "请求失败"
            await self.actions.send(
                group_id=self.event.group_id,
                user_id=self.event.user_id,
                message=Message(Text(txt))
            )





