from __future__ import annotations

import asyncio
import atexit
import contextlib
import logging
import os
import signal
import time

from patchright.async_api import BrowserContext, Page, Playwright, async_playwright
from patchright.async_api import TimeoutError as PlaywrightTimeoutError

_logger = logging.getLogger(__name__)

os.makedirs("./temps", exist_ok=True)

PROFILE_DIR = "./temps/patchright-profile"

# 页面加载等待上限（秒）。GitHub 等重页面的 load 事件经常等不到（轮询请求不断）。
LOAD_TIMEOUT = 40
# domcontentloaded 后等 networkidle 的预算（500ms 无网络活动 = 基本加载完成）。
SETTLE_TIMEOUT = 15
# networkidle 超时后的兜底固定等待（等异步 CSS 应用）。
STYLE_SETTLE = 3
# Cloudflare 自动挑战最多等待时间。
CHALLENGE_TIMEOUT = 20

_CHALLENGE_MARKERS = (
    "just a moment",
    "attention required",
    "verify you are human",
    "checking your browser",
    "enable javascript and cookies to continue",
    "cf-chl-",
    "cf-turnstile",
)

_driver_proc: asyncio.subprocess.Process | None = None


class CloudflareChallengeError(RuntimeError):
    """页面仍停留在 Cloudflare 自动挑战页。"""


def is_cloudflare_challenge(title: str, text: str) -> bool:
    """判断标题或正文是否命中 Cloudflare 挑战页特征。"""
    haystack = f"{title}\n{text}".lower()
    return any(marker in haystack for marker in _CHALLENGE_MARKERS)


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
    context: BrowserContext

    _context: BrowserContext | None = None
    _playwright: Playwright | None = None
    _lock = asyncio.Lock()

    @classmethod
    async def init(cls, headless: bool = True) -> Catcher:
        c = cls()
        c.context = await cls._get_context(headless)
        return c

    @classmethod
    async def _get_context(cls, headless: bool = True) -> BrowserContext:
        context = cls._context
        if context is not None:
            try:
                browser = context.browser
                if browser is None or browser.is_connected():
                    return context
            except Exception:
                pass
            _logger.warning("浏览器上下文已失效，重新启动")
            with contextlib.suppress(Exception):
                await context.close()
            cls._context = None

        async with cls._lock:
            if cls._context is not None:
                try:
                    browser = cls._context.browser
                    if browser is None or browser.is_connected():
                        return cls._context
                except Exception:
                    pass

            with contextlib.suppress(Exception):
                if cls._playwright is not None:
                    await cls._playwright.stop()
            cls._playwright = None

            pw = await async_playwright().start()
            cls._playwright = pw
            os.makedirs(PROFILE_DIR, exist_ok=True)
            cls._context = await pw.chromium.launch_persistent_context(
                user_data_dir=PROFILE_DIR,
                channel="chromium",
                headless=headless,
                args=["--disable-dev-shm-usage"],
                handle_sigint=False,
                handle_sigterm=False,
                handle_sighup=False,
            )
            _capture_driver_proc(pw)
            return cls._context

    async def catch(self, url: str, size: tuple[int, int] = (0, 0)) -> str:
        self.context = await self._get_context()
        return await asyncio.wait_for(self._catch(url, size), timeout=LOAD_TIMEOUT + 15)

    async def catch_text(self, url: str) -> tuple[str, str]:
        """真实渲染后提取网页正文文本,返回 (标题, 正文)。

        与 catch 共用共享浏览器与加载策略;正文优先取 main/article/[role=main] 容器,
        兜底 document.body.innerText,完整交给上层内容仓库处理。
        """
        self.context = await self._get_context()

        async def _do() -> tuple[str, str]:
            page = await self.context.new_page()
            try:
                await self._load(page, url)
                title = await page.title()
                text = await page.evaluate(
                    """() => {
                        const main = document.querySelector('main, article, [role="main"]');
                        const el = main || document.body;
                        return el.innerText || '';
                    }"""
                )
                return title, text
            finally:
                with contextlib.suppress(Exception):
                    await page.close()

        return await asyncio.wait_for(_do(), timeout=LOAD_TIMEOUT + 15)

    @staticmethod
    async def _on_challenge_page(page: Page) -> bool:
        try:
            title = await page.title()
        except Exception:
            title = ""
        try:
            text = await page.locator("body").inner_text(timeout=1000)
        except Exception:
            text = ""
        return is_cloudflare_challenge(title, text)

    @classmethod
    async def _wait_for_challenge(cls, page: Page) -> None:
        """给自动挑战留出完成时间；仍停留则抛出异常交给后续后备。"""
        deadline = time.monotonic() + CHALLENGE_TIMEOUT
        while await cls._on_challenge_page(page):
            if time.monotonic() >= deadline:
                raise CloudflareChallengeError("Cloudflare challenge did not complete")
            await asyncio.sleep(1)

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
        await Catcher._wait_for_challenge(page)

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
        page = await self.context.new_page()
        try:
            await self._load(page, url)
            try:
                return await self._screenshot(page, url, size)
            except Exception:
                _logger.warning("页面已失效，换新页面重试: %s", url)
                retry = await self.context.new_page()
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
        if self._context is not None:
            await self._context.close()
            type(self)._context = None
        if self._playwright is not None:
            await self._playwright.stop()
            type(self)._playwright = None
