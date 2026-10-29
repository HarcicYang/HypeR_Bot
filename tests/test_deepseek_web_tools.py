import unittest
from typing import Any, cast
from unittest.mock import AsyncMock, Mock, patch

from cfgr.manager import Serializers
from hyperot import configurator
from typing_extensions import override

try:
    configurator.BotConfig.get("hyper-bot")
except KeyError:
    configurator.BotConfig.load_from("config.json", Serializers.JSON, "hyper-bot")

from modules.AgentTools import deepseek_web, search_tools, webpage_tools  # noqa: E402
from modules.AgentTools.registry import ToolContext  # noqa: E402
from modules.AgentTools.search_tools import SearchTools  # noqa: E402
from modules.AgentTools.webpage_tools import WebpageTools  # noqa: E402


class DeepSeekWebToolTests(unittest.IsolatedAsyncioTestCase):
    @override
    def setUp(self) -> None:
        self.ctx = cast(ToolContext, cast(Any, object()))

    async def test_web_search_uses_deepseek_without_fallback(self) -> None:
        results = [
            {
                "title": "Example",
                "url": "https://example.com",
                "summary": "DeepSeek result",
            }
        ]
        with (
            patch.object(deepseek_web, "search", AsyncMock(return_value=results)) as deepseek_search,
            patch.object(search_tools, "_do_search") as fallback,
        ):
            result = await SearchTools().web_search(self.ctx, "example")

        self.assertIn("Example", result)
        deepseek_search.assert_awaited_once_with(self.ctx, "example", 5)
        fallback.assert_not_called()

    async def test_web_search_empty_result_does_not_fallback(self) -> None:
        with (
            patch.object(deepseek_web, "search", AsyncMock(return_value=[])),
            patch.object(search_tools, "_do_search") as fallback,
        ):
            result = await SearchTools().web_search(self.ctx, "missing")

        self.assertEqual(result, "没有找到与「missing」相关的结果")
        fallback.assert_not_called()

    async def test_web_search_falls_back_when_deepseek_unavailable(self) -> None:
        fallback_results = [
            {
                "title": "Fallback",
                "href": "https://fallback.example",
                "body": "Fallback result",
            }
        ]
        with (
            patch.object(
                deepseek_web,
                "search",
                AsyncMock(side_effect=deepseek_web.DeepSeekWebUnavailable("service down")),
            ),
            patch.object(search_tools, "_do_search", Mock(return_value=fallback_results)) as fallback,
        ):
            result = await SearchTools().web_search(self.ctx, "example")

        self.assertIn("Fallback", result)
        fallback.assert_called_once()

    async def test_read_webpage_uses_deepseek_before_local_chain(self) -> None:
        with (
            patch.object(webpage_tools, "_check_public_url", AsyncMock()),
            patch.object(
                deepseek_web, "fetch", AsyncMock(return_value=("Title", "DeepSeek content"))
            ) as deepseek_fetch,
            patch.object(webpage_tools, "_fetch_static", AsyncMock()) as static_fetch,
        ):
            result = await WebpageTools().read_webpage(self.ctx, "https://example.com/article")

        self.assertIn("读取方式：DeepSeek Fetch", result)
        self.assertIn("DeepSeek content", result)
        deepseek_fetch.assert_awaited_once_with(self.ctx, "https://example.com/article")
        static_fetch.assert_not_awaited()

    async def test_read_webpage_falls_back_when_deepseek_unavailable(self) -> None:
        with (
            patch.object(webpage_tools, "_check_public_url", AsyncMock()),
            patch.object(
                deepseek_web,
                "fetch",
                AsyncMock(side_effect=deepseek_web.DeepSeekWebUnavailable("service down")),
            ),
            patch.object(webpage_tools, "_fetch_static", AsyncMock(return_value=None)) as static_fetch,
            patch.object(webpage_tools.Catcher, "init", AsyncMock(side_effect=RuntimeError("browser down"))),
            patch.object(webpage_tools, "_jina_read", AsyncMock(return_value=None)),
        ):
            result = await WebpageTools().read_webpage(self.ctx, "https://example.com/article")

        self.assertIn("网页阅读失败", result)
        static_fetch.assert_awaited_once_with("https://example.com/article")

    async def test_deepseek_search_empty_results_are_valid(self) -> None:
        with patch.object(deepseek_web, "_post", AsyncMock(return_value={"results": []})) as post:
            result = await deepseek_web.search(self.ctx, "missing", 5)

        self.assertEqual(result, [])
        post.assert_awaited_once_with(
            self.ctx,
            deepseek_web.DEEPSEEK_SEARCH_PATH,
            {"query": "missing", "count": 5, "need_content": False},
            deepseek_web.DEEPSEEK_SEARCH_TIMEOUT,
        )

    async def test_deepseek_fetch_request_contract(self) -> None:
        with patch.object(
            deepseek_web,
            "_post",
            AsyncMock(return_value={"title": "Title", "content": "# Content"}),
        ) as post:
            title, content = await deepseek_web.fetch(self.ctx, "https://example.com/article")

        self.assertEqual((title, content), ("Title", "# Content"))
        post.assert_awaited_once_with(
            self.ctx,
            deepseek_web.DEEPSEEK_FETCH_PATH,
            {"url": "https://example.com/article"},
            deepseek_web.DEEPSEEK_FETCH_TIMEOUT,
        )


if __name__ == "__main__":
    unittest.main()
