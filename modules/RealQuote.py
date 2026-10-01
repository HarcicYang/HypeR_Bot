import httpx
from hyperot.v2 import Message, Text
from hyperot.v2.events import MessageReceivedEvent
from typing_extensions import override

from ModuleClass import Module, ModuleInfo, ModuleRegister


@ModuleRegister.register(MessageReceivedEvent)
class Quote(Module[MessageReceivedEvent]):
    @override
    @staticmethod
    def info() -> ModuleInfo:
        return ModuleInfo(
            is_hidden=False,
            module_name="Quote",
            desc="随机返回一条一言",
            helps="发送「一言」即可",
        )

    @override
    async def handle(self):
        if str(self.event.message) == "一言":
            response = httpx.get("https://international.v1.hitokoto.cn/")
            try:
                txt = f"{response.json()['hitokoto']} —— {response.json()['from_who']}, {response.json()['from']}"
            except Exception:
                txt = "请求失败"
            await self.api.scene(self.event.scene_type, self.event.scene_id).send(Message(Text(text=txt)))
