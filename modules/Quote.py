from Hyper import Segments
from Hyper.Manager import Message
from Hyper.Events import *
from ModuleClass import Module, ModuleInfo, ModuleRegister

# from PIL import Image, ImageDraw, ImageFont
from pyppeteer import launch
import os


# from io import BytesIO
# import httpx


# def open_from_url(url: str):
#     return Image.open(BytesIO(httpx.get(url).content))
#
#
# def square_scale(image: Image, height: int):
#     old_width, old_height = image.size
#     x = height / old_height
#     width = int(old_width * x)
#     return image.resize((width, height))


# def get_image(quote, ava_url, name):
#     mask = Image.open("assets/quote/mask.png").convert("RGBA")
#     background = Image.new('RGBA', mask.size, (255, 255, 255, 255))
#     head = open_from_url(ava_url).convert("RGBA")
#
#     title_font = ImageFont.truetype(r"assets\SourceHanSansSC-Bold-2.otf", size=36)
#     desc_font = ImageFont.truetype(r"assets\SourceHanSansSC-Regular-2.otf", size=20)
#     background.paste(square_scale(head, 640), (0, 0))
#     background.paste(mask, (0, 0), mask)
#     # background.show()
#     draw = ImageDraw.Draw(background)
#     text = String(quote).format(20)
#
#     draw.text((640, 165), text, font=title_font, fill=(255, 255, 255))
#     draw.text((862 if len(name) >= 7 else 1000, 465), f"——{name}", font=desc_font, fill=(112, 112, 112))
#     nbg = Image.new('RGB', mask.size, (0, 0, 0))
#     nbg.paste(background, (0, 0))
#     nbg.save("./temps/quote.png")

async def html2img(url: str) -> str:
    browser = await launch(
        headless=True,
        options={
            "handleSIGINT": False,
            "handleSIGTERM": False,
            "handleSIGHUP": False
        }
    )
    page = await browser.newPage()
    await page.goto(url)
    title = await page.title()
    await page.setViewport({"width": 1280, "height": 640})
    path = f"./temps/web_{title.replace(' ', '')}.png"
    await page.screenshot({"path": path})
    await browser.close()
    return path


async def get_image(quote, ava_url, name, uin):
    with open("./assets/quote.html", "r", encoding="utf-8") as f:
        html = f.read()

    html = html.replace("{ava_url}", ava_url)
    html = html.replace("{quote}", quote)
    html = html.replace("{name}", name)

    with open(f"./temps/quote_{uin}.html", "w", encoding="utf-8") as f:
        f.write(html)
    res = await html2img(f"file://{os.path.abspath(f'./temps/quote_{uin}.html')}")
    os.remove(f"./temps/quote_{uin}.html")
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
            if isinstance(self.event.message[0], Segments.Reply):
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
                    Segments.Reply(self.event.message_id),
                    Segments.Image(f"file://{os.path.abspath(res)}")
                )
            )
            os.remove(res)
