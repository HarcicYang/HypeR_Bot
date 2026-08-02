import asyncio
import contextlib
import logging
import os
import types
from collections.abc import Callable
from typing import Any

import websockets  # noqa: E402
import websockets.legacy.client as _legacy_client  # noqa: E402
from pyee import EventEmitter  # noqa: E402

_logger = logging.getLogger(__name__)


def _legacy_connect(uri: str, *args: Any, **kwargs: Any):
    kwargs.pop("loop", None)
    return _legacy_client.connect(uri, *args, **kwargs)


if not hasattr(websockets, "client"):
    websockets.client = types.SimpleNamespace(connect=_legacy_connect)  # type: ignore[attr-defined]


def _log_async_cb_exc(task: asyncio.Task[Any]) -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        _logger.error("pyppeteer 异步回调异常: %r", exc, exc_info=(type(exc), exc, exc.__traceback__))


def _emit_run(self: EventEmitter, f: Callable[..., Any], args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
    result = f(*args, **kwargs)
    if asyncio.iscoroutine(result):
        task = asyncio.ensure_future(result)
        task.add_done_callback(_log_async_cb_exc)


EventEmitter._emit_run = _emit_run  # type: ignore[method-assign]

from pyppeteer import launch  # noqa: E402
from pyppeteer.browser import Browser  # noqa: E402
from pyppeteer.errors import BrowserError  # noqa: E402
from pyppeteer.launcher import Launcher  # noqa: E402

# 原版 _get_ws_endpoint 是无限 while 循环 + 同步 time.sleep：Chrome 僵死时永久阻塞
# 事件循环（asyncio 超时也救不了，计时器无法运行），整个 bot 卡死。加 60s 上限。
_orig_get_ws_endpoint = Launcher._get_ws_endpoint


def _bounded_get_ws_endpoint(self: Launcher) -> str:
    import json as _json
    import time as _time
    from urllib.error import URLError
    from urllib.request import urlopen

    url = self.url + "/json/version"
    deadline = _time.time() + 60
    while self.proc.poll() is None and _time.time() < deadline:
        _time.sleep(0.1)
        try:
            with urlopen(url) as f:
                data = _json.loads(f.read().decode())
            return data["webSocketDebuggerUrl"]
        except URLError:
            continue
    raise BrowserError(f"Browser 启动超时或已退出，无法连接调试端口 {url}")


Launcher._get_ws_endpoint = _bounded_get_ws_endpoint  # type: ignore[method-assign]

os.makedirs("./temps", exist_ok=True)


# 共享浏览器后 quit() 不再被调用方执行；进程退出时事件循环已关闭，pyppeteer 的
# atexit（异步 killChrome）无法运行，这里同步终止 Chrome 进程避免残留
def _kill_browser_on_exit() -> None:
    browser = Catcher._browser
    if browser is not None and browser.process is not None:
        try:
            browser.process.terminate()
            browser.process.wait(timeout=5)
        except Exception:
            pass


import atexit  # noqa: E402

atexit.register(_kill_browser_on_exit)

# 页面加载等待上限（秒）。等待 load 事件——HTML/CSS/同步 JS 就绪，样式保证完整；
# networkidle2 对持续轮询的页面（如 GitHub）永远等不到，不能用
LOAD_TIMEOUT = 40


class Catcher:
    browser: Browser

    _browser: Browser | None = None

    @classmethod
    async def init(cls, headless: bool = True) -> "Catcher":
        """返回共享浏览器的 Catcher。浏览器进程全局复用，避免每次截图启动/退出 Chromium。"""
        c = cls()
        c.browser = await cls._get_browser(headless)
        return c

    @classmethod
    async def _get_browser(cls, headless: bool = True) -> Browser:
        if cls._browser is not None:
            return cls._browser
        cls._browser = await launch(
            headless=headless,
            # 项目位于外部挂载盘（nosuid），Chrome 的 SUID sandbox 无法使用，
            # 否则 renderer 启动即崩溃（CDP errorCode 159）
            args=["--no-sandbox", "--disable-dev-shm-usage"],
            # autoClose=False：pyppeteer 的 atexit 是异步 killChrome，事件循环关闭后
            # 必然失败；由下方同步 _kill_browser_on_exit 全权负责退出清理
            options={
                "autoClose": False,
                "handleSIGINT": False,
                "handleSIGTERM": False,
                "handleSIGHUP": False,
            },
        )
        return cls._browser

    async def catch(self, url: str, size: tuple[int, int] = (0, 0)) -> str:
        # 整体超时兜底：pyppeteer 0.0.25 的 launch 内部是同步 while 循环 + time.sleep，
        # 异常挂起时无法被 asyncio 取消；此处保证单次截图有明确的时间上限，不阻塞消息处理
        return await asyncio.wait_for(self._catch(url, size), timeout=LOAD_TIMEOUT + 15)

    @staticmethod
    async def _load(page: Any, url: str) -> None:
        """限时加载页面：等待 load 事件（HTML/CSS/同步 JS 就绪，样式保证完整）。
        超时后不重试导航——对同一 URL 重复导航会被 Chrome 拒绝（Target closed），
        主动 stopLoading 让页面可交互（否则导航中状态会阻塞后续 CDP 调用），截当前状态。
        仅当导航本身失败（连接拒绝等 PageError）时才重试一次。
        """
        try:
            await page.goto(url, {"waitUntil": "load", "timeout": LOAD_TIMEOUT * 1000})
            return
        except TimeoutError:
            _logger.warning("load 超时（%.0fs），截取当前状态: %s", LOAD_TIMEOUT, url)
        except Exception as e:
            _logger.warning("导航失败，重试一次: %r", e)
            try:
                await page.goto(url, {"waitUntil": "load", "timeout": LOAD_TIMEOUT * 1000})
                return
            except Exception as e2:
                _logger.warning("重试也失败，截取当前状态: %r", e2)
        with contextlib.suppress(Exception):
            await page._client.send("Page.stopLoading")

    async def _catch(self, url: str, size: tuple[int, int]) -> str:
        page = await self.browser.newPage()
        try:
            await self._load(page, url)
            title = await page.title()
            path = f"./temps/web_{''.join([str(ord(i)) for i in title][:12])}.png"
            opt = {"path": path}
            if size[0] == size[1] == 0:
                await page.setViewport({"width": 1080, "height": 250})
                height = await page.evaluate("document.body.scrollHeight")
                await page.setViewport({"width": 1080, "height": height})
            else:
                await page.setViewport({"width": size[0], "height": size[1]})

            os.makedirs("./temps", exist_ok=True)
            await page.screenshot(opt)
            return path
        finally:
            # 页面可能已被 Chrome 关闭（导航异常时），close 失败会掩盖原始错误
            with contextlib.suppress(Exception):
                await page.close()

    async def quit(self) -> None:
        """关闭共享浏览器（进程退出时调用即可）。"""
        if self._browser is not None:
            await self._browser.close()
            type(self)._browser = None
