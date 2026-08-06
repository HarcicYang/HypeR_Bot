from __future__ import annotations

import asyncio
import atexit
import contextlib
import logging
import os
import signal
import time

from playwright.async_api import Browser, Page, Playwright, async_playwright
from playwright.async_api import TimeoutError as PlaywrightTimeoutError

_logger = logging.getLogger(__name__)

os.makedirs("./temps", exist_ok=True)

# 页面加载等待上限（秒）。GitHub 等重页面的 load 事件经常等不到（轮询请求不断）。
LOAD_TIMEOUT = 40
# domcontentloaded 后等 networkidle 的预算（500ms 无网络活动 = 基本加载完成）。
SETTLE_TIMEOUT = 15
# networkidle 超时后的兜底固定等待（等异步 CSS 应用）。
STYLE_SETTLE = 3

_driver_proc: asyncio.subprocess.Process | None = None


def file_url(path: str) -> str:
    return "file://" + os.path.abspath(path).replace("\\", "/")


def _capture_driver_proc(pw: Playwright) -> None:
    global _driver_proc
    _driver_proc = None
    with contextlib.suppress(Exception):
        _driver_proc = pw._impl_obj._connection._transport._proc  # type: ignore[attr-defined]


def _direct_children(pid: int) -> list[int]:
    children: list[int] = []
    try:
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            try:
                with open(f"/proc/{entry}/stat", encoding="ascii") as f:
                    fields = f.read().rsplit(")", 1)[-1].split()
                if int(fields[1]) == pid:
                    children.append(int(entry))
            except (OSError, ValueError, IndexError):
                continue
    except OSError:
        pass
    return children


def _kill_browser_on_exit() -> None:
    proc = _driver_proc
    if proc is None or proc.pid is None:
        return
    pid = proc.pid
    try:
        os.kill(pid, 0)
    except OSError:
        return
    for child in _direct_children(pid):
        with contextlib.suppress(OSError):
            os.kill(child, signal.SIGKILL)
    with contextlib.suppress(OSError):
        os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + 5
    while True:
        try:
            os.kill(pid, 0)
        except OSError:
            break
        if time.monotonic() > deadline:
            with contextlib.suppress(OSError):
                os.kill(pid, signal.SIGKILL)
            break
        time.sleep(0.2)


atexit.register(_kill_browser_on_exit)


class Catcher:
    browser: Browser

    _browser: Browser | None = None
    _playwright: Playwright | None = None
    _lock = asyncio.Lock()

    @classmethod
    async def init(cls, headless: bool = True) -> Catcher:
        c = cls()
        c.browser = await cls._get_browser(headless)
        return c

    @classmethod
    async def _get_browser(cls, headless: bool = True) -> Browser:
        browser = cls._browser
        if browser is not None:
            try:
                if browser.is_connected():
                    return browser
            except Exception:
                pass
            _logger.warning("浏览器实例已失效，重新启动")
            with contextlib.suppress(Exception):
                await browser.close()
            cls._browser = None

        async with cls._lock:
            if cls._browser is not None:
                try:
                    if cls._browser.is_connected():
                        return cls._browser
                except Exception:
                    pass

            with contextlib.suppress(Exception):
                if cls._playwright is not None:
                    await cls._playwright.stop()
            cls._playwright = None

            pw = await async_playwright().start()
            cls._playwright = pw
            cls._browser = await pw.chromium.launch(
                headless=headless,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
                handle_sigint=False,
                handle_sigterm=False,
                handle_sighup=False,
            )
            _capture_driver_proc(pw)
            return cls._browser

    async def catch(self, url: str, size: tuple[int, int] = (0, 0)) -> str:
        self.browser = await self._get_browser()
        return await asyncio.wait_for(self._catch(url, size), timeout=LOAD_TIMEOUT + 15)

    @staticmethod
    async def _load(page: Page, url: str) -> None:
        for attempt in (1, 2):
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=LOAD_TIMEOUT * 1000)
                break
            except Exception as e:
                if attempt == 1:
                    _logger.warning("导航失败，重试一次: %r", e)
                else:
                    _logger.warning("重试也失败，截取当前状态: %r", e)
        try:
            await page.wait_for_load_state("networkidle", timeout=SETTLE_TIMEOUT * 1000)
        except PlaywrightTimeoutError:
            await asyncio.sleep(STYLE_SETTLE)

    @staticmethod
    async def _screenshot(page: Page, url: str, size: tuple[int, int]) -> str:
        title = await page.title()
        path = f"./temps/web_{''.join([str(ord(i)) for i in title][:12])}.png"
        if size[0] == size[1] == 0:
            await page.set_viewport_size({"width": 1080, "height": 250})
            height = await page.evaluate("document.body.scrollHeight")
            await page.set_viewport_size({"width": 1080, "height": height})
        else:
            await page.set_viewport_size({"width": size[0], "height": size[1]})
        os.makedirs("./temps", exist_ok=True)
        await page.screenshot(path=path)
        return path

    async def _catch(self, url: str, size: tuple[int, int]) -> str:
        page = await self.browser.new_page()
        try:
            await self._load(page, url)
            try:
                return await self._screenshot(page, url, size)
            except Exception:
                _logger.warning("页面已失效，换新页面重试: %s", url)
                retry = await self.browser.new_page()
                try:
                    await self._load(retry, url)
                    return await self._screenshot(retry, url, size)
                finally:
                    with contextlib.suppress(Exception):
                        await retry.close()
        finally:
            with contextlib.suppress(Exception):
                await page.close()

    async def quit(self) -> None:
        if self._browser is not None:
            await self._browser.close()
            type(self)._browser = None
