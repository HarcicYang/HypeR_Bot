"""Browserless 远程截图客户端。"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx
from hyperot import configurator

config = configurator.BotConfig.get("hyper-bot")

DEFAULT_ENDPOINT = "https://production-sfo.browserless.io"
SCREENSHOT_TIMEOUT = 60.0


class BrowserlessError(RuntimeError):
    """Browserless 请求失败。"""


class BrowserlessNotConfigured(BrowserlessError):
    """缺少 Browserless API Token。"""


async def _request_screenshot(payload: dict[str, Any], timeout: float) -> bytes:
    token = str(config.others.get("browserless_token") or "").strip()
    if not token:
        raise BrowserlessNotConfigured("未配置 config.others.browserless_token")

    endpoint = str(config.others.get("browserless_endpoint") or DEFAULT_ENDPOINT).strip().rstrip("/")
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                endpoint + "/screenshot",
                params={"token": token},
                headers={
                    "Accept": "image/png,image/jpeg,image/webp",
                    "Cache-Control": "no-cache",
                },
                json=payload,
            )
    except httpx.HTTPError as exc:
        raise BrowserlessError(f"请求失败: {type(exc).__name__}") from exc

    if response.status_code != 200:
        raise BrowserlessError(f"HTTP {response.status_code}")
    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if not content_type.startswith("image/") or not response.content:
        raise BrowserlessError(f"响应不是图片: {content_type or 'unknown'}")
    return response.content


async def screenshot_url(
    url: str,
    *,
    width: int = 1280,
    height: int = 900,
    timeout: float = SCREENSHOT_TIMEOUT,
) -> bytes:
    """通过 Browserless 截取网页，返回图片字节。"""
    if urlparse(url).scheme not in {"http", "https"}:
        raise BrowserlessError("截图 URL 必须是 HTTP(S)")

    payload = {
        "url": url,
        "gotoOptions": {"waitUntil": "domcontentloaded", "timeout": 30_000},
        "waitForSelector": {"selector": "main", "timeout": 10_000},
        "waitForTimeout": 1_000,
        "bestAttempt": True,
        "scrollPage": True,
        "selector": "main",
        "viewport": {"width": width, "height": height},
        "options": {"type": "png"},
    }
    return await _request_screenshot(payload, timeout)


async def screenshot_html(
    html: str,
    *,
    width: int = 1280,
    height: int = 640,
    full_page: bool = False,
    wait_ms: int = 500,
    timeout: float = SCREENSHOT_TIMEOUT,
) -> bytes:
    """通过 Browserless 渲染 HTML，返回 PNG 字节。"""
    payload = {
        "html": html,
        "waitForFunction": {
            "fn": "() => document.fonts.status === 'loaded' && Array.from(document.images).every(img => img.complete)",
            "timeout": 10_000,
        },
        "waitForTimeout": wait_ms,
        "bestAttempt": True,
        "viewport": {"width": width, "height": height},
        "options": {"type": "png", "fullPage": full_page},
    }
    return await _request_screenshot(payload, timeout)
