from Hyper import Segments
from Hyper.Manager import Message
from Hyper.Events import *
from Hyper.ModuleClass import Module, ModuleInfo, ModuleRegister
from PIL import Image, ImageDraw, ImageFont
import os
from modules.WebsiteServices import open_from_url, square_scale


def wrap_text(text, chars_per_line=13):
    lines = [text[i:i + chars_per_line] for i in range(0, len(text), chars_per_line)]
    return '\n'.join(lines)


def get_image(quote, ava_url, name):
    mask = Image.open("assets/quote/mask.png").convert("RGBA")
    background = Image.new('RGBA', mask.size, (255, 255, 255, 255))
    head = open_from_url(ava_url).convert("RGBA")

    title_font = ImageFont.truetype(r"assets\SourceHanSansSC-Bold-2.otf", size=36)
    desc_font = ImageFont.truetype(r"assets\SourceHanSansSC-Regular-2.otf", size=20)
    background.paste(square_scale(head, 640), (0, 0))
    background.paste(mask, (0, 0), mask)
    # background.show()
    draw = ImageDraw.Draw(background)
    text = wrap_text(quote)

    draw.text((640, 165), text, font=title_font, fill=(255, 255, 255))
    draw.text((862 if len(name) >= 7 else 1000, 465), f"——{name}", font=desc_font, fill=(112, 112, 112))
    nbg = Image.new('RGB', mask.size, (0, 0, 0))
    nbg.paste(background, (0, 0))
    nbg.save("./temps/quote.png")


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
            if isinstance(self.event.message[0], Segments.Reply):
                msg_id = self.event.message[0].id
            else:
                return

            content = await self.actions.get_msg(msg_id)
            name = content.data["sender"]["nickname"] if not content.data["sender"].get("card") else \
                content.data["sender"]["card"]
            uin = content.data["sender"]["user_id"]
            message = content.data["message"]
            message = gen_message({"message": message})
            text = str(message)
            get_image(text, f"http://q2.qlogo.cn/headimg_dl?dst_uin={uin}&spec=640", name)
            await self.actions.send(
                group_id=self.event.group_id,
                user_id=self.event.user_id,
                message=Message(
                    Segments.Reply(self.event.message_id),
                    Segments.Image(f"file://{os.path.abspath('./temps/quote.png')}")
                )
            )
