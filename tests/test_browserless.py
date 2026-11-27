import unittest
from unittest.mock import AsyncMock, Mock, patch

from cfgr.manager import Serializers
from hyperot import configurator
from typing_extensions import override

try:
    configurator.BotConfig.get("hyper-bot")
except KeyError:
    configurator.BotConfig.load_from("config.json", Serializers.JSON, "hyper-bot")

from modules import browserless  # noqa: E402


class BrowserlessTests(unittest.IsolatedAsyncioTestCase):
    @override
    def setUp(self) -> None:
        self.client = AsyncMock()
        self.client.__aenter__.return_value = self.client
        self.client.__aexit__.return_value = None
        self.response = Mock(
            status_code=200,
            headers={"content-type": "image/png"},
            content=b"image-bytes",
        )
        self.client.post.return_value = self.response

    async def test_screenshot_url_posts_expected_request(self) -> None:
        settings = {
            "browserless_token": "test-token",
            "browserless_endpoint": "https://browserless.example",
        }
        with (
            patch.dict(browserless.config.others, settings),
            patch.object(browserless.httpx, "AsyncClient", return_value=self.client) as client_factory,
        ):
            result = await browserless.screenshot_url("https://github.com/HarcicYang/HypeR_Bot")

        self.assertEqual(result, b"image-bytes")
        client_factory.assert_called_once_with(timeout=browserless.SCREENSHOT_TIMEOUT)
        call = self.client.post.await_args
        self.assertEqual(call.args, ("https://browserless.example/screenshot",))
        self.assertEqual(call.kwargs["params"], {"token": "test-token"})
        self.assertEqual(call.kwargs["json"]["url"], "https://github.com/HarcicYang/HypeR_Bot")
        self.assertEqual(call.kwargs["json"]["selector"], "main")
        self.assertEqual(call.kwargs["json"]["options"], {"type": "png"})

    async def test_screenshot_url_requires_token(self) -> None:
        with (
            patch.dict(browserless.config.others, {"browserless_token": ""}),
            self.assertRaises(browserless.BrowserlessNotConfigured),
        ):
            await browserless.screenshot_url("https://github.com/HarcicYang/HypeR_Bot")

    async def test_screenshot_html_posts_expected_request(self) -> None:
        settings = {
            "browserless_token": "test-token",
            "browserless_endpoint": "https://browserless.example",
        }
        with (
            patch.dict(browserless.config.others, settings),
            patch.object(browserless.httpx, "AsyncClient", return_value=self.client),
        ):
            result = await browserless.screenshot_html(
                "<html>render</html>",
                width=720,
                height=480,
                full_page=True,
                wait_ms=1_200,
            )

        self.assertEqual(result, b"image-bytes")
        call = self.client.post.await_args
        self.assertEqual(call.kwargs["json"]["html"], "<html>render</html>")
        self.assertNotIn("url", call.kwargs["json"])
        self.assertEqual(call.kwargs["json"]["viewport"], {"width": 720, "height": 480})
        self.assertEqual(call.kwargs["json"]["waitForTimeout"], 1_200)
        self.assertEqual(call.kwargs["json"]["options"], {"type": "png", "fullPage": True})


if __name__ == "__main__":
    unittest.main()
