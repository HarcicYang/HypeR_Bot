# import httpx
import uuid
import requests as httpx
import asyncio
import aiohttp
import threading
from bilibili_api import video
from PIL import Image
from io import BytesIO
from flask import Flask, Response
from pyppeteer import launch
from pyppeteer.browser import Browser
from pyppeteer.page import Page


async def fetch(url: str) -> bytes:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.content.read()


async def open_from_url(url: str):
    # return Image.open(BytesIO(httpx.get(url, verify=False).content))
    return Image.open(BytesIO(await fetch(url)))


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


app = Flask(__name__)

url_cache = {}
browser: Browser
page: Page
loop = asyncio.get_event_loop()

@app.route("/img/<method>/<file>")
async def get_img(method: str, file: str) -> Response:
    if method == "url":
        # return Response(httpx.get(url_cache[file]).content, mimetype="image/webp")
        return Response(await fetch(url_cache[file]), mimetype="image/webp")
        # return Response(url_cache[file], mimetype="image/png")
    elif method == "file":
        with open(f"../../temps/{file}", "rb") as f:
            return Response(f.read(), mimetype="image/png")

    return Response(bytes(404))


@app.route("/tmp/<bv_id>")
async def gen_page(bv_id: str) -> str:
    info = await video_info(bv_id)
    cover = await open_from_url(info.picture)
    if cover.size[0] < 1020 or cover.size[1] < 1080 or cover.size[1] > 1500 or cover.size[0] > 1250:
        cover = square_scale(cover, 1200)
    url_cache[bv_id] = cover.size
    cover.save(f"../../temps/cover_{bv_id}.png")
    cover = f"http://127.0.0.1/img/file/cover_{bv_id}.png"
    played_times = num_format(info.views)
    likes_text = num_format(info.likes)
    coins_text = num_format(info.coins)
    favorites_text = num_format(info.favorites)

    with open("../../assets/bilibili/bili.html", encoding="utf-8") as f:
        html_tmp = f.read()

    nid = str(uuid.uuid4()).replace("-", "")
    url_cache[nid] = (info.uploader_face + "@12q.webp").replace("i0.hdslb.com", "i1.hdslb.com")
    # print(url_cache)
    # url_cache[nid] = httpx.get(info.uploader_face + "@.webp").content


    html_tmp = (
        html_tmp
        .replace("{[bv]}", bv_id)
        .replace("{[cover]}", cover)
        .replace("{[head_img]}", f"http://127.0.0.1/img/url/{nid}")
        # .replace("{[head_img]}", url_cache[nid])
        .replace("{[name]}", info.uploader)
        .replace("{[plays]}", played_times)
        .replace("{[likes]}", likes_text)
        .replace("{[coins]}", coins_text)
        .replace("{[favorites]}", favorites_text)
        .replace("{[title]}", info.title)
        .replace("{[desc]}", info.desc)
    )

    return html_tmp


@app.route("/gen/<bv_id>")
async def gen_result(bv_id: str) -> Response:
    async def inner() -> Response:
        # print(1919180)
        if url_cache.get(f"file_{bv_id}"):
            path = url_cache.get(f"file_{bv_id}")
        else:
            await page.goto(f"http://127.0.0.1/tmp/{bv_id}")
            title = await page.title()
            path = f"../../temps/web_{''.join([str(ord(i)) for i in title][:12])}.png"
            opt = {"path": path}
            size = url_cache[bv_id]
            await page.setViewport({"width": size[0], "height": size[1]})
            await page.screenshot(opt)

            url_cache[f"file_{bv_id}"] = path
        with open(path, "rb") as f:
            return Response(f.read(), mimetype="image/png")

    # print(future.done())
    # # print(future.result())
    return asyncio.run_coroutine_threadsafe(inner(), loop).result()
    # return loop.run_until_complete(inner())


@app.route("/video/<bv_id>")
def ret(bv_id: str) -> str:
    return url_cache.get(f"video_{bv_id}", "")

class Info:
    def __init__(self, info: dict):
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


async def video_info(bv: str) -> Info:
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
                "view": 0,
                "reply": 0,
                "like": 0,
                "coin": 0,
                "favorite": 0,
            },
            "desc": err.__str__()
        }
        d_urls = []

    url_cache[f"video_{bv}"] = "" if len(d_urls) == 0 else d_urls[0]["url"]
    return Info(info)


async def main():
    global browser, page
    browser = await launch(
        headless=True, options={
            "handleSIGINT": False,
            "handleSIGTERM": False,
            "handleSIGHUP": False
        }
    )
    page = await browser.newPage()


loop.run_until_complete(main())
threading.Thread(target=lambda: app.run("127.0.0.1", 80, debug=False)).start()
loop.run_forever()

