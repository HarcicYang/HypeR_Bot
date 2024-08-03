from Hyper import Manager, ModuleClass, Segments, WordSafety, Logic
from Hyper.Events import *
import re
from bilibili_api import video
import os
from io import BytesIO
import httpx
import json
from PIL import Image
from pyppeteer import launch


def open_from_url(url: str):
    return Image.open(BytesIO(httpx.get(url).content))


def square_scale(image: Image, height: int):
    old_width, old_height = image.size
    x = height / old_height
    width = int(old_width * x)
    return image.resize((width, height))


def num_format(number: int) -> str:
    units = ['k', 'M', 'B', 'T']
    suffix = ''
    if number >= 1000:
        magnitude = 0
        while abs(number) >= 1000 and magnitude < len(units):
            magnitude += 1
            number /= 1000.0
            suffix = units[magnitude - 1]

    if number == int(number):
        formatted_number = str(int(number)) + suffix
    else:
        formatted_number = f"{number:.2f}{suffix}"
    return formatted_number


async def html2img(url: str, size: tuple[int, int]) -> str:
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
    await page.setViewport({"width": size[0], "height": size[1]})
    path = f"./temps/web_{title.replace(' ', '')}.png"
    await page.screenshot({"path": path})
    await browser.close()
    return path


@Logic.Cacher(1).cache_async
async def get_image(info) -> str:
    cover = open_from_url(info.picture)
    if cover.size[0] < 1020 or cover.size[1] < 1080 or cover.size[1] > 1500 or cover.size[0] > 1250:
        cover = square_scale(cover, 1200)
    size = cover.size
    cover.save("./temps/cover.png")
    cover = f"file://{os.path.abspath('./temps/cover.png')}"
    played_times = num_format(info.views)
    likes_text = num_format(info.likes)
    coins_text = num_format(info.coins)
    favorites_text = num_format(info.favorites)

    with open("./assets/bilibili/bili.html", encoding="utf-8") as f:
        html_tmp = f.read()

    html_tmp = html_tmp.replace("{[cover]}", cover)
    html_tmp = html_tmp.replace("{[head_img]}", info.uploader_face)
    html_tmp = html_tmp.replace("{[name]}", info.uploader)
    html_tmp = html_tmp.replace("{[plays]}", played_times)
    html_tmp = html_tmp.replace("{[likes]}", likes_text)
    html_tmp = html_tmp.replace("{[coins]}", coins_text)
    html_tmp = html_tmp.replace("{[favorites]}", favorites_text)
    html_tmp = html_tmp.replace("{[title]}", info.title)
    html_tmp = html_tmp.replace("{[desc]}", info.desc)

    with open("./temps/bilibili.html", "w", encoding="utf-8") as f:
        f.write(html_tmp)

    return await html2img(f"file://{os.path.abspath('./temps/bilibili.html')}", size)


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
    try:
        v = video.Video(bvid=bv)
        info = await v.get_info()
    except Exception as err:
        info = {
            "pic": "https://i0.hdslb.com/bfs/new_dyn/7afd4c057eba6152836a52fbb4b126e9686607596.png",
            "title": f"(╯°□°）╯︵ ┻━┻ {err.__dict__.get('msg') or '?????'}",
            "owner": {
                "name": "蜀黍",
                "face": "https://i2.hdslb.com/bfs/app/8920e6741fc2808cce5b81bc27abdbda291655d3.png@240w_240h_1c_1s_!web-avatar-search-videos.webp"
            },
            "stat": {
                "view": 114514,
                "reply": 0,
                "like": 191,
                "coin": 91,
                "favorite": 80,
            },
            "desc": err.__str__()
        }

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


class GithubSafetyResult:
    def __init__(self, safe: bool, address: str):
        self.safe: bool = safe
        self.address: str = address


@Logic.Cacher().cache
def github_safety_check(url: str) -> GithubSafetyResult:
    urls = url.split("/")
    base_index = None
    for i in urls:
        if i == "github.com":
            base_index = urls.index(i)
            break
    if not base_index:
        return GithubSafetyResult(False, urls[base_index])
    repo = f"https://api.github.com/repos/{urls[base_index + 1]}/{urls[base_index + 2]}"
    response = httpx.get(repo, verify=False)
    desc = str(response.json()["description"])
    result = WordSafety.check(text=desc)
    ret = GithubSafetyResult(result.result, f"{urls[base_index + 1]}/{urls[base_index + 2]}")
    return ret


@ModuleClass.ModuleRegister.register(GroupMessageEvent, PrivateMessageEvent)
class Module(ModuleClass.Module):
    async def handle(self):
        if self.event.blocked or self.event.servicing or self.event.is_silent:
            return
        try:
            if len(self.event.message) != 0 and isinstance(self.event.message[0], Segments.Json):
                json_data = json.loads(self.event.message[0].data)
                bv_id = get_bv(text=str(json_data))
            else:
                bv_id = get_bv(text=str(self.event.message))
        except AttributeError:
            return

        if bv_id:
            info = await video_info(bv=bv_id)
            path = await get_image(info)
            result = Manager.Message([Segments.Image(f"file://{os.path.abspath(path)}", f"{info.title}")])

            await self.actions.send(group_id=self.event.group_id, message=result)

        pa = r"(http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+\b)"
        try:
            url = re.search(pa, str(self.event.message)).group()
        except:
            return
        if "github.com/" in url:
            safety = github_safety_check(url=url)
            if not safety.safe:
                return
            content = url.replace("github.com/", "opengraph.githubassets.com/Yenai/")
            with open("./temps/github.png", "wb") as f:
                f.write(httpx.get(content).content)
            await self.actions.send(group_id=self.event.group_id, user_id=self.event.user_id, message=Manager.Message(
                [Segments.Image(f"file://{os.path.abspath('./temps/github.png')}", summary=f"{safety.address}")]
            ))
