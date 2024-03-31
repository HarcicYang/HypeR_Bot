from lib import Manager, ModuleClass, Segments, WordSafety, Logic
import re
from bilibili_api import video
import os
from io import BytesIO
import httpx
from PIL import Image, ImageDraw, ImageFont


def open_from_url(url: str):
    return Image.open(BytesIO(httpx.get(url).content))


def square_scale(image: Image, height: int):
    old_width, old_height = image.size
    x = height / old_height
    width = int(old_width * x)
    return image.resize((width, height))


@Logic.Cacher(1).cache
def get_image(info):
    old = Image.open("assets/bilibili/back.png")
    background = Image.new('RGBA', old.size, (255, 255, 255, 255))
    background.paste(old)
    cover = open_from_url(info.picture)
    head = open_from_url(info.uploader_face)
    mask = Image.open("assets/bilibili/mask.png")
    draw = ImageDraw.Draw(background)
    title_font = ImageFont.truetype(r"assets\SourceHanSansSC-Bold-2.otf", size=33)
    desc_font = ImageFont.truetype(r"assets\SourceHanSansSC-Regular-2.otf", size=13)
    background.paste(square_scale(cover, 540), (9, 9))
    background.paste(square_scale(head, 32), (9, 625))
    draw.text((12, 553), info.title, font=title_font, fill=(0, 0, 0))
    draw.text((12, 599), info.desc.replace("\n", " | "), font=desc_font, fill=(0, 0, 0))
    draw.text((50, 629), info.uploader, font=desc_font, fill=(0, 187, 255))

    times = Image.open("assets/bilibili/times.png")
    likes = Image.open("assets/bilibili/likes.png")
    coins = Image.open("assets/bilibili/coins.png")
    favorites = Image.open("assets/bilibili/favorites.png")
    played_times = str(info.views)
    likes_text = str(info.likes)
    coins_text = str(info.coins)
    favorites_text = str(info.favorites)

    background.paste(times, (12, 670))
    draw.text((44, 665), played_times, font=desc_font, fill=(0, 0, 0))
    background.paste(likes, (144, 662))
    draw.text((176, 665), likes_text, font=desc_font, fill=(0, 0, 0))
    background.paste(coins, (276, 662))
    draw.text((308, 665), coins_text, font=desc_font, fill=(0, 0, 0))
    background.paste(favorites, (408, 662))
    draw.text((440, 665), favorites_text, font=desc_font, fill=(0, 0, 0))
    background.paste(mask, mask=mask)

    background.save("bili.png")


@Logic.Cacher().cache
def get_bv(text: str):
    bv_pattern = r"BV[a-zA-Z0-9]{10,12}"
    if "b23.tv" in text:
        pa = r"https:\/\/b23\.tv\/[a-zA-Z0-9\-_]+"
        url = re.search(pa, text)
        if not url:
            return None
        else:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.149 Safari/537.36"
            }
            response = httpx.get(url.group(), headers=headers)

            bv = re.search(bv_pattern, response.text)
    else:
        bv = re.search(bv_pattern, text)
    return bv.group() if bv else None


@Logic.Cacher().cache_async
async def video_info(bv: str):
    v = video.Video(bvid=bv)
    info = await v.get_info()

    class Info:
        def __init__(self):
            self.picture = info["pic"]
            self.title = info["title"]
            self.uploader = info["owner"]["name"]
            self.uploader_face = info["owner"]["face"]
            self.views = info["stat"]["view"]
            self.replies = info["stat"]["reply"]
            self.likes = info["stat"]["like"]
            self.coins = info["stat"]["coin"]
            self.favorites = info["stat"]["favorite"]
            self.desc = info["desc"]

    return Info()


@Logic.Cacher().cache
def github_safety_check(url: str) -> bool:
    urls = url.split("/")
    base_index = None
    for i in urls:
        if i == "github.com":
            base_index = urls.index(i)
            break
    if not base_index:
        return False
    repo = f"https://api.github.com/repos/{urls[base_index + 1]}/{urls[base_index + 2]}"
    response = httpx.get(repo, verify=False)
    desc = str(response.json()["description"])
    result = WordSafety.check(text=desc)
    return result.result


@ModuleClass.ModuleRegister.register(["message"])
class Module(ModuleClass.Module):
    async def handle(self):
        if self.event.blocked or self.event.servicing:
            return
        try:
            bv_id = get_bv(text=str(self.event.message))
        except AttributeError:
            return

        if bv_id:
            info = await video_info(bv=bv_id)
            get_image(info)
            result = Manager.Message([Segments.Image(f"file://{os.path.abspath('bili.png')}")])

            self.actions.send(group_id=self.event.group_id, message=result)

        pa = r"(http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+\b)"
        try:
            url = re.search(pa, str(self.event.message)).group()
        except:
            return
        if "github.com/" in url:
            if not github_safety_check(url=url):
                return
            content = url.replace("github.com/", "opengraph.githubassets.com/Yenai/")
            self.actions.send(group_id=self.event.group_id, user_id=self.event.user_id, message=Manager.Message(
                [Segments.Image(content)]
            ))

        elif "bilibili.com/video/" in url or "b23.tv/" in url:
            pass
        else:
            return
