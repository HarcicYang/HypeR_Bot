from hyperot import segments
from hyperot.common import Message
from hyperot.events import *
from ModuleClass import Module, ModuleInfo, ModuleRegister

import os

from modules.site_catch import Catcher


async def get_image(quote, ava_url, name, uin):
    catcher = await Catcher.init()
    with open("./assets/quote.html", "r", encoding="utf-8") as f:
        html = f.read()

    html = html.replace("{ava_url}", ava_url)
    html = html.replace("{quote}", quote)
    html = html.replace("{name}", name)

    with open(f"./temps/quote_{uin}.html", "w", encoding="utf-8") as f:
        f.write(html)
    # res = await html2img(f"file://{os.path.abspath(f'./temps/quote_{uin}.html')}")
    res = await catcher.catch(f"file://{os.path.abspath(f'./temps/quote_{uin}.html')}", (1280, 640))
    os.remove(f"./temps/quote_{uin}.html")
    await catcher.quit()
    return res


@ModuleRegister.register(GroupMessageEvent)
class Quoter(Module):
    @staticmethod
    def info() -> ModuleInfo:
        return ModuleInfo(
            is_hidden=False,
            module_name="Quoter",
            author="Harcic#8042",
            desc="生成对名言之伟大引用",
            helps="引用你要生成的消息，然后在消息框中输入“.quote”，哇！中了！"
        )

    async def handle(self):
        if ".quote" in str(self.event.message):
            if isinstance(self.event.message[0], segments.Reply):
                msg_id = self.event.message[0].id
            else:
                return

            content = await self.actions.get_msg(msg_id)
            name = content.data.sender.nickname if not content.data.sender.card else \
                content.data.sender.card
            uin = content.data.sender.user_id
            message = content.data.message
            text = str(message)
            res = await get_image(text, f"http://q2.qlogo.cn/headimg_dl?dst_uin={uin}&spec=640", name, uin)
            await self.actions.send(
                group_id=self.event.group_id,
                user_id=self.event.user_id,
                message=Message(
                    segments.Reply(self.event.message_id),
                    segments.Image(f"file://{os.path.abspath(res)}")
                )
            )
            os.remove(res)
