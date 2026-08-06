import httpx
from hyperot.common import Message
from hyperot.events import MessageEvent
from hyperot.segments import Text
from typing_extensions import override

from ModuleClass import Module, ModuleInfo, ModuleRegister


@ModuleRegister.register(MessageEvent)
class Quote(Module[MessageEvent]):
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
            await self.actions.send_msg(
                group_id=self.event.group_id, user_id=self.event.user_id, message=Message(Text(txt))
            )
