import os

from hyperot import segments
from hyperot.common import Message
from hyperot.events import *
from typing_extensions import override

from ModuleClass import Module, ModuleInfo, ModuleRegister
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


@ModuleRegister.register(GroupMessageEvent)
class Quoter(Module[GroupMessageEvent]):
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
        if ".quote" in str(self.event.message):
            if isinstance(self.event.message[0], segments.Reply):
                msg_id = self.event.message[0].id
            else:
                return

            content = await self.actions.get_msg(int(msg_id))
            sender = content.data.sender
            name = (sender.card if isinstance(sender, GroupSender) and sender.card else sender.nickname) or "未知用户"
            uin = content.data.sender.user_id
            if uin is None:
                return
            message = content.data.message
            text = str(message)
            res = await get_image(text, f"http://q2.qlogo.cn/headimg_dl?dst_uin={uin}&spec=640", name, uin)
            await self.actions.send_msg(
                group_id=self.event.group_id,
                user_id=self.event.user_id,
                message=Message(segments.Reply(self.event.message_id), segments.Image(file_url(res))),
            )
            os.remove(res)
