import os
from typing import Any

from hyperot.v2 import Image, Message
from hyperot.v2 import Quote as QuoteSegment
from hyperot.v2.events import MessageReceivedEvent
from typing_extensions import override

from ModuleClass import Module, ModuleInfo, ModuleRegister, group_message
from modules.site_catch import Catcher, file_url


async def get_image(quote: str, ava_url: str, name: str, uin: int) -> str:
    catcher = await Catcher.init()  # 共享浏览器，进程内只启动一次
    try:
        with open("./assets/quote.html", encoding="utf-8") as f:
            html = f.read()

        html = html.replace("{ava_url}", ava_url)
        html = html.replace("{quote}", quote)
        html = html.replace("{name}", name)

        with open(f"./temps/quote_{uin}.html", "w", encoding="utf-8") as f:
            f.write(html)
        return await catcher.catch(file_url(f"./temps/quote_{uin}.html"), (1280, 640))
    finally:
        os.remove(f"./temps/quote_{uin}.html")


@ModuleRegister.register(MessageReceivedEvent)
class Quoter(Module[MessageReceivedEvent]):
    @override
    @staticmethod
    def filter(event: Any, allowed: list[Any]) -> bool:
        return group_message(event)

    @override
    @staticmethod
    def info() -> ModuleInfo:
        return ModuleInfo(
            is_hidden=False,
            module_name="Quoter",
            author="Harcic#8042",
            desc="生成对名言之伟大引用",
            helps="引用你要生成的消息，然后在消息框中输入“.quote”，哇！中了！",
        )

    @override
    async def handle(self):
        if ".quote" not in str(self.event.message):
            return
        if not len(self.event.message) or not isinstance(self.event.message[0], QuoteSegment):
            return
        msg_id = int(self.event.message[0].message_id)

        content = await self.api.message(str(msg_id)).fetch()
        text = str(content)
        # get_msg 的原始响应带 sender（昵称/名片），类型化 fetch 只返回消息本体，故这里走 raw。
        raw = await self.api.raw("get_msg", {"message_id": msg_id})
        payload: Any = raw.data
        data = payload if isinstance(payload, dict) else dict[str, Any]()
        sender: dict[str, Any] = data.get("sender") or dict[str, Any]()
        name = (sender.get("card") if sender.get("card") else sender.get("nickname")) or "未知用户"
        uin = sender.get("user_id")
        if uin is None:
            return
        res = await get_image(text, f"http://q2.qlogo.cn/headimg_dl?dst_uin={uin}&spec=640", name, uin)
        await self.api.scene(self.event.scene_type, self.event.scene_id).send(
            Message(QuoteSegment(message_id=str(self.event.message_id)), Image(source=file_url(res)))
        )
        os.remove(res)
