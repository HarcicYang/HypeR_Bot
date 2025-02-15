import asyncio
import aiohttp
import io
import re
import time
import gzip
import hypercorn.asyncio
from ping3 import ping
from PIL import Image
from io import BytesIO
from quart import Quart, Response
from pyppeteer import launch
from pyppeteer.browser import Browser
from pyppeteer.page import Page
from concurrent.futures import ThreadPoolExecutor

page_pool = asyncio.Queue()
thread_pool = ThreadPoolExecutor(max_workers=4)


def ping_host(ip: str) -> int:
    ip_address = ip
    response = ping(ip_address)
    if response is not None:
        delay = int(response * 1000)
        return delay
    return 1145141919180


class BHostSelection:
    def __init__(self, hosts: list) -> None:
        self.hosts = hosts
        self.host: str = ""

    def select(self) -> None:
        pings = {}
        for i in self.hosts:
            pings[i] = ping_host(i)
        self.host = list(pings.keys())[list(pings.values()).index(min(pings.values()))]

    def fix(self, url: str) -> str:
        for i in self.hosts:
            url = url.replace(i, self.host)
        return url


sel = BHostSelection(["i0.hdslb.com", "i1.hdslb.com", "i2.hdslb.com"])
sel.select()
print(f"using bilibili img host {sel.host}")


class Timer:
    def __init__(self, name: str):
        self.name = name
        self.start: float

    def __enter__(self) -> None:
        self.start = time.time()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        print(f"{self.name} done: {time.time() - self.start}")
        del self


async def get_page() -> Page:
    return await page_pool.get()


async def return_page(page: Page) -> None:
    await page_pool.put(page)


async def fetch(url: str) -> bytes:
    async with aiohttp.ClientSession() as session:
        async with session.get(sel.fix(url)) as response:
            return await response.content.read()


async def fetch_json(url: str) -> dict:
    async with aiohttp.ClientSession() as session:
        async with session.get(
                url, headers={
                    "User-Agent": ""
                }
        ) as response:
            return await response.json()


async def open_from_url(url: str) -> Image.Image:
    return Image.open(BytesIO(await fetch(url)))


def square_scale(image: Image.Image, height: int):
    old_width, old_height = image.size
    x = height / old_height
    width = int(old_width * x)
    return image.resize((width, height), Image.Resampling.LANCZOS)


def img_byte(img: Image.Image) -> bytes:
    bf = BytesIO()
    img.save(bf, format="WEBP", quality=12, optimize=True)
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


def minify_html(html: str) -> str:
    html = re.sub(r"<!--.*?-->", "", html)
    html = re.sub(r"\s+", " ", html)
    html = re.sub(r">\s+<", "><", html)
    return html.strip()


async def compress(response: Response) -> Response:
    with Timer("compress"):
        gzip_buffer = io.BytesIO()
        with gzip.GzipFile(mode="wb", fileobj=gzip_buffer, compresslevel=5) as gzip_file:
            gzip_file.write(await response.data)
        response.data = gzip_buffer.getvalue()
        response.headers["Content-Encoding"] = "gzip"
        response.headers["Content-Length"] = len(await response.data)
        return response


async def async_image_operation(func, *args):
    return await asyncio.get_event_loop().run_in_executor(thread_pool, func, *args)


async def square_scale_async(image: Image.Image, height: int):
    return await async_image_operation(square_scale, image, height)


async def img_byte_async(img: Image.Image):
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
        res = await compress(Response(url_cache.copy()[file], mimetype="image/webp"))
        del url_cache[file]
        return res

    return Response(bytes(404))


with open("../../assets/bilibili/bili.html", encoding="utf-8") as f:
    html_tmp = minify_html(f.read())


async def cover_verify(url: str) -> Image.Image:
    img = await open_from_url(url)
    if img.size[1] < img.size[0] < 10 * 150:
        h = int(img.size[1] * ((10 * 150) / img.size[0]))
        img = await square_scale_async(img, h)
    elif img.size[1] > img.size[0] and img.size[0] < 5 * 150:
        img = await square_scale_async(img, 5 * 150)
    return img


async def fetch_resources(info: "Info") -> tuple[Image.Image, Image.Image]:
    with Timer("fetch-resources"):
        # cover_future = asyncio.create_task(open_from_url(info.picture + "@8q.webp"))
        cover_future = asyncio.create_task(cover_verify(info.picture + "@8q.webp"))
        avatar_future = asyncio.create_task(open_from_url(info.uploader_face + "@170w_170h_8q.webp"))
        await asyncio.gather(cover_future, avatar_future)
        return cover_future.result(), avatar_future.result()


@app.route("/tmp/<bv_id>")
async def gen_page(bv_id: str) -> Response:
    with Timer("gen-page-ss"):
        global html_tmp
        info, ok = await video_info(bv_id)
        cover_avatar_future = asyncio.create_task(fetch_resources(info))
        cover_text = f"http://127.0.0.1:8080/img/file/cover_{bv_id}.webp"
        avatar_text = f"http://127.0.0.1:8080/img/file/avatar_{bv_id}.webp"
        played_times = num_format(info.views)
        likes_text = num_format(info.likes)
        coins_text = num_format(info.coins)
        favorites_text = num_format(info.favorites)

        n_html_tmp = (
            html_tmp
            .replace("{bv}", bv_id)
            .replace("{cover}", cover_text)
            .replace("{head_img}", avatar_text)
            .replace("{name}", info.uploader)
            .replace("{plays}", played_times)
            .replace("{likes}", likes_text)
            .replace("{coins}", coins_text)
            .replace("{favorites}", favorites_text)
            .replace("{title}", info.title)
            .replace("{desc}", info.desc)
        )
        await cover_avatar_future
        cover, avatar = cover_avatar_future.result()
        url_cache[bv_id] = cover.size
        url_cache[f"{bv_id}_ok"] = ok
        url_cache[f"cover_{bv_id}.webp"] = img_byte(cover)
        url_cache[f"avatar_{bv_id}.webp"] = img_byte(avatar)
        return await compress(Response(minify_html(n_html_tmp)))


async def write(buffer: bytes, path: str) -> None:
    with open(path, mode="wb") as bfr:
        bfr.write(buffer)


@app.route("/gen/<bv_id>")
async def gen_result(bv_id: str) -> Response:
    with Timer("gen-full"):
        if url_cache.get(f"file_{bv_id}"):
            with open(url_cache.get(f"file_{bv_id}"), "rb") as f:
                return Response(f.read(), mimetype="image/jpeg")
        else:
            page = await get_page()
            with Timer("get-page"):
                await page.goto(f"http://127.0.0.1:8080/tmp/{bv_id}", waitUntil="networkidle0")
            title = await page.title()
            path = f"../../temps/web_{''.join([str(ord(i)) for i in title][:12])}.png"
            opt = {"path": None, "quality": 18, "omitBackground": True, "type": "jpeg"}
            size = url_cache.copy()[bv_id]
            del url_cache[bv_id]
            await page.setViewport({"width": size[0], "height": size[1]})
            bf = await page.screenshot(opt)
            await return_page(page)
            if url_cache[f"{bv_id}_ok"]:
                url_cache[f"file_{bv_id}"] = path
                del url_cache[f"{bv_id}_ok"]
                asyncio.create_task(write(bf, path))
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
    with Timer("get-info"):
        try:
            info = await fetch_json(f"https://api.bilibili.com/x/web-interface/view?bvid={bv}")
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
            "handleSIGHUP": False,
        },
        args=[
            "--disable-gpu",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--no-zygote",
            "--disable-setuid-sandbox",
            "--disable-extensions",
            "--disable-software-rasterizer",
            "--disable-background-timer-throttling",
            "--disable-renderer-backgrounding"
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
