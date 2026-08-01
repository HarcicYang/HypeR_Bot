import json
import os
import re
from typing import override

import httpx
from hyperot import common, segments
from hyperot.events import *
from PIL import Image

import ModuleClass
from modules.bili_renderer import fetch_resources, render, video_info
from modules.site_catch import Catcher


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
                m = re.search(bv_pattern, response.text)
                if m is None:
                    continue
                bv = m.group()
                bv_list.append(bv)
    else:
        bv = re.findall(bv_pattern, text)
        bv_list += bv
    return bv_list or None


class GitHubView:
    def __init__(self, author: str | None = None, repo: str | None = None):
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

    async def auto(self, url: str) -> Image.Image:
        self.parse(url)
        url_parts = url.split("/")
        if (code := "issues") in url_parts:
            idx = url_parts.index(code)
            if idx + 1 < len(url_parts) and url_parts[idx + 1].isdigit():
                return await self.iss(url_parts[idx + 1])
        elif (code := "pull") in url_parts:
            idx = url_parts.index(code)
            if idx + 1 < len(url_parts) and url_parts[idx + 1].isdigit():
                if idx + 2 < len(url_parts) and url_parts[idx + 2] == "files":
                    return await self.pull_diff(url_parts[idx + 1])
                return await self.pull(url_parts[idx + 1])
        elif (code := "commit") in url_parts:
            idx = url_parts.index(code)
            if idx + 1 < len(url_parts):
                return await self.commit(url_parts[idx + 1])

        return await self.repo_page(url)

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
        parts = url.split("/")
        for i, part in enumerate(parts):
            if part != "github.com":
                continue
            if i + 3 > len(parts):
                break
            author = parts[i + 1]
            repo = parts[i + 2]
            base = f"https://opengraph.githubassets.com/Yenai/{author}/{repo}"

            if i + 3 < len(parts):
                sub = parts[i + 3]
                if sub == "issues" and i + 4 < len(parts) and parts[i + 4].isdigit():
                    return f"{base}/issues/{parts[i + 4]}"
                if sub == "pull" and i + 4 < len(parts) and parts[i + 4].isdigit():
                    return f"{base}/pull/{parts[i + 4]}"
                if sub == "commit" and i + 4 < len(parts):
                    return f"{base}/commit/{parts[i + 4]}"
            return base
        return url

    async def iss(self, code: str) -> Image.Image:
        url = f"https://github.com/{self.author}/{self.repo}/issues/{code}"
        pth = await self._get(url)
        img = Image.open(pth)
        img = img.crop((0, 75, img.size[0], img.size[1] - 220))
        return img

    async def pull(self, code: str) -> Image.Image:
        url = f"https://github.com/{self.author}/{self.repo}/pull/{code}"
        pth = await self._get(url)
        img = Image.open(pth)
        img = img.crop((0, 75, img.size[0], img.size[1] - 220))
        return img

    async def pull_diff(self, code: str) -> Image.Image:
        url = f"https://github.com/{self.author}/{self.repo}/pull/{code}/files"
        pth = await self._get(url)
        img = Image.open(pth)
        img = img.crop((0, 75, img.size[0], img.size[1] - 150))
        return img

    async def commit(self, code: str) -> Image.Image:
        url = f"https://github.com/{self.author}/{self.repo}/commit/{code}"
        pth = await self._get(url)
        img = Image.open(pth)
        img = img.crop((0, 75, img.size[0], img.size[1] - 150))
        return img

    async def repo_page(self, url: str) -> Image.Image:
        url = f"https://github.com/{self.author}/{self.repo}"
        pth = await self._get(url)
        img = Image.open(pth)
        img = img.crop((0, 75, img.size[0], img.size[1] - 220))
        return img


@ModuleClass.ModuleRegister.register(GroupMessageEvent, PrivateMessageEvent)
class Module(ModuleClass.Module[GroupMessageEvent | PrivateMessageEvent]):
    @override
    @staticmethod
    def info() -> ModuleClass.ModuleInfo:
        return ModuleClass.ModuleInfo(
            is_hidden=False,
            module_name="WebsiteServices",
            desc="自动解析并展示网页链接预览",
            helps="无需显式命令，消息中含有以下内容时自动触发：\n- Bilibili BV号 / b23.tv短链 → 生成视频信息卡片\n- GitHub 仓库/issue/PR/commit 链接 → 生成预览图",
        )

    @override
    async def handle(self):
        if self.event.blocked or self.event.is_silent:
            return
        try:
            if len(self.event.message) != 0 and isinstance(self.event.message[0], segments.Json):
                json_data = json.loads(str(self.event.message[0].data))
                bv_id = get_bv(text=str(json_data))
            else:
                bv_id = get_bv(text=str(self.event.message))
        except AttributeError:
            return

        if bv_id:
            for i in bv_id:
                try:
                    data, ok = await video_info(bv=i)
                    cover, avatar = await fetch_resources(data)
                    jpeg_bytes = render(data, cover, avatar)
                    path = f"./temps/bili_{i}.jpg"
                    with open(path, "wb") as f:
                        f.write(jpeg_bytes)
                    await self.actions.send_msg(
                        group_id=self.event.group_id,
                        message=common.Message(
                            segments.Image(
                                "file://" + os.path.abspath(path).replace("\\", "/"), summary=data.get("title", "")
                            )
                        ),
                    )
                except Exception as e:
                    import traceback as _tb

                    print(f"渲染B站视频 {i} 失败: {e}\n{_tb.format_exc()}")

        pa = r"(http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+\b)"
        try:
            urls = re.findall(pa, str(self.event.message))
            for i in urls:
                if "github.com/" in i:
                    ghv = GitHubView()
                    ghv.parse(i)
                    await self.actions.send_msg(
                        group_id=self.event.group_id,
                        user_id=self.event.user_id,
                        message=common.Message(segments.Image(ghv.head_any(i), summary=f"{ghv.author}/{ghv.repo}")),
                    )
                    try:
                        (await ghv.auto(i)).save(f"./temps/github_{ghv.author}_{ghv.repo}.png")
                        await self.actions.send_msg(
                            group_id=self.event.group_id,
                            user_id=self.event.user_id,
                            message=common.Message(
                                segments.Image(
                                    "file://" + os.path.abspath(f"./temps/github_{ghv.author}_{ghv.repo}.png"),
                                    summary=f"{ghv.author}/{ghv.repo}",
                                )
                            ),
                        )
                        os.remove(f"./temps/github_{ghv.author}_{ghv.repo}.png")
                    except NotImplementedError:
                        pass
        except Exception:
            return
