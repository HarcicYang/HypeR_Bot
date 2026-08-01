import asyncio
import sys
from typing import Any

from pyppeteer import launch

args = sys.argv
content = args[1]
output = args[2]


async def wait_for_network_idle(page: Any, timeout: int = 30000) -> None:
    await page.waitForNavigation({"waitUntil": "networkidle2", "timeout": timeout})


async def html_to_image(html_content: str, output_path: str) -> None:
    browser = await launch(headless=True)
    page = await browser.newPage()
    await page.setContent(html_content)
    await wait_for_network_idle(page)
    await page.screenshot({"path": output_path})
    await browser.close()


with open(content, encoding="utf-8") as f:
    content = f.read()

asyncio.run(html_to_image(html_content=content, output_path=output))
