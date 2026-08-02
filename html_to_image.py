import asyncio
import logging
import sys
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

args = sys.argv
content = args[1]
output = args[2]


async def html_to_image(html_content: str, output_path: str) -> None:
    browser = await launch(
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage"],
    )
    page = await browser.newPage()
    await page.setContent(html_content)
    await page.waitForFunction("document.readyState === 'complete'", {"timeout": 30000})
    await page.screenshot({"path": output_path})
    await browser.close()


with open(content, encoding="utf-8") as f:
    content = f.read()

asyncio.run(html_to_image(html_content=content, output_path=output))
