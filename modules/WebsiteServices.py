from Hyper import Segments
import ModuleClass
from Hyper.Utils import Logic
from Hyper.Utils.Logic import Downloader
from Hyper.Events import *

from typing import Any
import re
from bilibili_api import video
import os
from io import BytesIO
import httpx
import json
from PIL import Image
from PIL.ImageFile import ImageFile

from modules.site_catch import Catcher


def open_from_url(url: str):
    return Image.open(BytesIO(httpx.get(url, verify=False).content))


def square_scale(image: Image, height: int):
    old_width, old_height = image.size
    x = height / old_height
    width = int(old_width * x)
    return image.resize((width, height))


@Logic.Cacher().cache
def get_bv(text: str):
    bv_pattern = r"BV[a-zA-Z0-9]{10,12}"
    bv_list = []
    if "b23.tv" in text:
        pa = r"https:\/\/b23\.tv\/[a-zA-Z0-9\-_]+"
        urls = re.findall(pa, text)
        if not len(urls):
            return None
        else:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.149 Safari/537.36"
            }
            for i in urls:
                response = httpx.get(i, headers=headers)
                bv = re.search(bv_pattern, response.text).group()
                bv_list.append(bv)
    else:
        bv = re.findall(bv_pattern, text)
        bv_list += bv
    return bv_list or None


@Logic.Cacher().cache_async
async def video_info(bv: str) -> tuple[Any, dict]:
    try:
        retried = 0
        while 1:
            try:
                v = video.Video(bvid=bv)
                d_urls = (await v.get_download_url(0, html5=True)).get("durl") or []
                info = await v.get_info()
                break
            except Exception as e:
                retried += 1
                if retried == 5:
                    raise e

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
        d_urls = []

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

    return Info(), d_urls


class GitHubView:
    def __init__(self, author: str = None, repo: str = None):
        self.author = author
        self.repo = repo

    def parse(self, repo: str) -> "GitHubView":
        url = repo.split("/")
        base_index = None
        for i in url:
            if i == "github.com":
                base_index = url.index(i)
                break
        if not base_index:
            return self
        self.author = url[base_index + 1]
        self.repo = url[base_index + 2]
        return self

    async def auto(self, url: str) -> ImageFile:
        self.parse(url)
        url = url.split("/")
        if (code := "issues") in url:
            return await self.iss(url[url.index(code) + 1])
        elif (code := "pull") in url:
            if url[url.index(code) + 2] == "files":
                return await self.pull_diff(url[url.index(code) + 1])
            return await self.pull(url[url.index(code) + 1])
        elif (code := "commit") in url:
            return await self.commit(url[url.index(code) + 1])
        else:
            raise NotImplementedError()

    @staticmethod
    async def _get(url: str) -> str:
        cth = await Catcher.init()
        # pth = await cth.catch("https://github.com/LagrangeDev/Lagrange.Core/issues/444")
        # pth = await cth.catch("https://github.com/LagrangeDev/Lagrange.Core/pull/703")
        pth = await cth.catch(url)
        await cth.quit()
        return pth

    def head(self) -> str:
        return f"https://opengraph.githubassets.com/Yenai/{self.author}/{self.repo}"

    @staticmethod
    def head_any(url: str) -> str:
        return url.replace("github.com/", "opengraph.githubassets.com/Yenai/")

    async def iss(self, code: str) -> ImageFile:
        url = f"https://github.com/{self.author}/{self.repo}/issues/{code}"
        pth = await self._get(url)
        img = Image.open(pth)
        img = img.crop((0, 75, img.size[0], img.size[1] - 220))
        return img

    async def pull(self, code: str) -> ImageFile:
        url = f"https://github.com/{self.author}/{self.repo}/pull/{code}"
        pth = await self._get(url)
        img = Image.open(pth)
        img = img.crop((0, 75, img.size[0], img.size[1] - 220))
        return img

    async def pull_diff(self, code: str) -> ImageFile:
        url = f"https://github.com/{self.author}/{self.repo}/pull/{code}/files"
        pth = await self._get(url)
        img = Image.open(pth)
        img = img.crop((0, 75, img.size[0], img.size[1] - 150))
        return img

    async def commit(self, code: str) -> ImageFile:
        url = f"https://github.com/{self.author}/{self.repo}/commit/{code}"
        pth = await self._get(url)
        img = Image.open(pth)
        img = img.crop((0, 75, img.size[0], img.size[1] - 150))
        return img


@ModuleClass.ModuleRegister.register(GroupMessageEvent, PrivateMessageEvent)
class Module(ModuleClass.Module):
    async def handle(self):
        if self.event.blocked or self.event.is_silent:
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
            for i in bv_id:
                info = await video_info(bv=i)
                result = Comm.Message(
                    Segments.Image(f"http://127.0.0.1/gen/{i}", summary=info[0].title)
                )

                await self.actions.send(group_id=self.event.group_id, message=result)
                if len(info[1]) != 0:
                    url = info[1][0].get("url")
                    if url:
                        if not os.path.exists(f"./temps/b_video_{bv_id}.mp4"):
                            dlr = Downloader(url, f"./temps/b_video_{bv_id}.mp4", 1, True)
                            ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
                            await dlr.download(ua)
                        msg = Comm.Message(Segments.Video.build(f"./temps/b_video_{bv_id}.mp4"))
                        await self.actions.send(group_id=self.event.group_id, message=msg)
                        # os.remove(f"./temps/b_video_{bv_id}.mp4")

                # os.remove(path)

        pa = r"(http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+\b)"
        try:
            urls = re.findall(pa, str(self.event.message))
            for i in urls:
                if "github.com/" in i:
                    ghv = GitHubView()
                    ghv.parse(i)
                    await self.actions.send(
                        group_id=self.event.group_id,
                        user_id=self.event.user_id,
                        message=Comm.Message(
                            Segments.Image(ghv.head_any(i), summary=f"{ghv.author}/{ghv.repo}")
                        )
                    )
                    try:
                        (await ghv.auto(i)).save(f"./temps/github_{ghv.author}_{ghv.repo}.png")
                        await self.actions.send(
                            group_id=self.event.group_id,
                            user_id=self.event.user_id,
                            message=Comm.Message(
                                Segments.Image(
                                    "file://" + os.path.abspath(f"./temps/github_{ghv.author}_{ghv.repo}.png"),
                                    summary=f"{ghv.author}/{ghv.repo}")
                            )
                        )
                        os.remove(f"./temps/github_{ghv.author}_{ghv.repo}.png")
                    except NotImplementedError:
                        pass
        except:
            return
