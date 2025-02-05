import asyncio
import aiohttp
import json
import io
import re
import gzip
import hypercorn.asyncio
from PIL import Image
from io import BytesIO
from quart import Quart, Response
from pyppeteer import launch
from pyppeteer.browser import Browser
from pyppeteer.page import Page
from concurrent.futures import ThreadPoolExecutor

page_pool = asyncio.Queue()
thread_pool = ThreadPoolExecutor(max_workers=4)


async def get_page() -> Page:
    return await page_pool.get()


async def return_page(page: Page) -> None:
    await page.goto("about:blank")
    await page_pool.put(page)


async def fetch(url: str) -> bytes:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.content.read()


async def fetch_json(url: str) -> dict:
    async with aiohttp.ClientSession() as session:
        async with session.get(
                url, headers={
                    "Accept": "application/json",
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 Edg/133.0.0.0"
                }
        ) as response:
            return json.loads(await response.text())


async def open_from_url(url: str) -> Image:
    return Image.open(BytesIO(await fetch(url)))


def square_scale(image: Image, height: int):
    old_width, old_height = image.size
    x = height / old_height
    width = int(old_width * x)
    return image.resize((width, height), Image.Resampling.LANCZOS)


def img_byte(img: Image) -> bytes:
    bf = BytesIO()
    img.save(bf, format="WEBP", quality=65, optimize=True)
    bf.seek(0)
    return bf.read()


def num_format(number: int) -> str:
    units = ['', 'k', 'M', 'B', 'T']
    if number < 1000:
        return str(number)

    magnitude = min(len(units) - 1, int((len(str(number)) - 1) / 3))
    number /= 1000.0 ** magnitude
    suffix = units[magnitude]

    if number == int(number):
        return f"{int(number)}{suffix}"
    else:
        return f"{number:.2f}{suffix}"


async def fetch_resources(info: "Info") -> tuple[Image, Image]:
    cover_future = open_from_url(info.picture)
    avatar_future = open_from_url(info.uploader_face + "@12q.webp")
    cover, avatar = await asyncio.gather(cover_future, avatar_future)
    return cover, avatar


def minify_html(html: str) -> str:
    html = re.sub(r"<!--.*?-->", "", html)
    html = re.sub(r"\s+", " ", html)
    html = re.sub(r">\s+<", "><", html)
    return html.strip()


async def compress(response: Response) -> Response:
    gzip_buffer = io.BytesIO()
    with gzip.GzipFile(mode="wb", fileobj=gzip_buffer) as gzip_file:
        gzip_file.write(await response.data)
    response.data = gzip_buffer.getvalue()
    response.headers["Content-Encoding"] = "gzip"
    response.headers["Content-Length"] = len(await response.data)
    return response


async def async_image_operation(func, *args):
    return await asyncio.get_event_loop().run_in_executor(thread_pool, func, *args)


async def square_scale_async(image: Image, height: int):
    return await async_image_operation(square_scale, image, height)


async def img_byte_async(img: Image):
    return await async_image_operation(img_byte, img)


app = Quart(__name__)

url_cache = {}
browser: Browser
loop = asyncio.get_event_loop()


@app.route("/img/<method>/<file>")
async def get_img(method: str, file: str) -> Response:
    if method == "url":
        return Response(bytes(404))
    elif method == "file":
        res = Response(url_cache.copy()[file], mimetype="image/webp")
        del url_cache[file]
        return res

    return Response(bytes(404))


with open("../../assets/bilibili/bili.html", encoding="utf-8") as f:
    html_tmp = f.read()


@app.route("/tmp/<bv_id>")
async def gen_page(bv_id: str) -> Response:
    global html_tmp
    info, ok = await video_info(bv_id)
    cover, avatar = await fetch_resources(info)
    if cover.size[0] < 1020 or cover.size[1] < 1080 or cover.size[1] > 1500 or cover.size[0] > 1200:
        cover = await square_scale_async(cover, 1125)
    url_cache[bv_id] = cover.size
    url_cache[f"{bv_id}_ok"] = ok
    url_cache[f"cover_{bv_id}.webp"] = await img_byte_async(cover)
    url_cache[f"avatar_{bv_id}.webp"] = await img_byte_async(avatar)
    cover = f"http://127.0.0.1:8080/img/file/cover_{bv_id}.webp"
    avatar = f"http://127.0.0.1:8080/img/file/avatar_{bv_id}.webp"
    played_times = num_format(info.views)
    likes_text = num_format(info.likes)
    coins_text = num_format(info.coins)
    favorites_text = num_format(info.favorites)

    n_html_tmp = (
        html_tmp
        .replace("{bv}", bv_id)
        .replace("{cover}", cover)
        .replace("{head_img}", avatar)
        .replace("{name}", info.uploader)
        .replace("{plays}", played_times)
        .replace("{likes}", likes_text)
        .replace("{coins}", coins_text)
        .replace("{favorites}", favorites_text)
        .replace("{title}", info.title)
        .replace("{desc}", info.desc)
    )

    return await compress(Response(minify_html(n_html_tmp)))


@app.route("/gen/<bv_id>")
async def gen_result(bv_id: str) -> Response:
    if url_cache.get(f"file_{bv_id}"):
        with open(url_cache.get(f"file_{bv_id}"), "rb") as f:
            return Response(f.read(), mimetype="image/jpeg")
    else:
        page = await get_page()
        await page.goto(f"http://127.0.0.1:8080/tmp/{bv_id}")
        title = await page.title()
        path = f"../../temps/web_{''.join([str(ord(i)) for i in title][:12])}.png"
        opt = {"path": path, "quality": 70, "omitBackground": True, "type": "jpeg"}
        size = url_cache.copy()[bv_id]
        del url_cache[bv_id]
        await page.setViewport({"width": size[0], "height": size[1]})
        bf = await page.screenshot(opt)
        await return_page(page)
        if url_cache[f"{bv_id}_ok"]:
            url_cache[f"file_{bv_id}"] = path
            del url_cache[f"{bv_id}_ok"]
        return Response(bf, mimetype="image/jpeg")


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


class BVideoException(Exception):
    def __init__(self, info):
        self.info = info


async def video_info(bv: str) -> tuple[Info, bool]:
    try:
        info = (await fetch_json(f"https://api.bilibili.com/x/web-interface/view?bvid={bv}"))
        if info["code"] != 0:
            raise BVideoException(info.get("message"))
        info = info["data"]
        ok = True
    except BVideoException as err:
        info = {
            "pic": "https://i0.hdslb.com/bfs/new_dyn/7afd4c057eba6152836a52fbb4b126e9686607596.png",
            "title": f"(╯°□°）╯︵ ┻━┻ {err.info or '?????'}",
            "owner": {
                "name": "",
                "face": "https://i0.hdslb.com/bfs/app/8920e6741fc2808cce5b81bc27abdbda291655d3.png"
            },
            "stat": {
                "view": -1,
                "reply": -1,
                "like": -1,
                "coin": -1,
                "favorite": -1,
            },
            "desc": ""
        }
        ok = False
    return Info(info), ok


async def main():
    global browser
    browser = await launch(
        headless=True,
        options={
            "handleSIGINT": False,
            "handleSIGTERM": False,
            "handleSIGHUP": False
        },
        args=[
            "--disable-gpu",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            # "--single-process",
            "--no-zygote",
            "--disable-setuid-sandbox"
        ],
        ignoreHTTPSWarnings=True,
        ignoreHTTPSErrors=True,
        defaultViewport=None
    )
    for i in range(3):
        await page_pool.put(await browser.newPage())
    cfg = hypercorn.Config()
    cfg.bind = ["127.0.0.1:8080"]
    cfg.worker_class = "uvloop"
    cfg.logLevel = "DEBUG"
    await hypercorn.asyncio.serve(app, cfg)


loop.run_until_complete(main())
