from pyppeteer import launch
from pyppeteer.browser import Browser
import asyncio


class Catcher:
    browser: Browser

    @classmethod
    async def init(cls, headless: bool = True) -> "Catcher":
        c = cls()
        c.browser = await launch(
            headless=headless, options={
                "handleSIGINT": False,
                "handleSIGTERM": False,
                "handleSIGHUP": False
            }
        )
        return c

    async def catch(self, url: str, size: tuple[int, int] = (0, 0)) -> str:
        page = await self.browser.newPage()
        await page.goto(url)
        title = await page.title()
        path = f"./temps/web_{''.join([str(ord(i)) for i in title][:12])}.png"
        opt = {"path": path}
        if size[0] == size[1] == 0:
            await page.setViewport({"width": 1080, "height": 250})
            height = await page.evaluate("document.body.scrollHeight")
            await page.setViewport({"width": 1080, "height": height})
        else:
            await page.setViewport({"width": size[0], "height": size[1]})

        await page.screenshot(opt)
        await page.close()
        return path

    async def quit(self) -> None:
        await self.browser.close()

