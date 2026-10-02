"""render_html Agent 工具的参数、输出、清理和网络策略测试。"""

from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
import time
import types
import unittest
from typing import Any, cast

from typing_extensions import override

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_render_tools() -> Any:
    """加载 render 工具及 site_catch,绕开 modules/__init__.py 的模块扫描。"""
    if "test_render_tools_module" in sys.modules:
        return sys.modules["test_render_tools_module"]
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    stubs: dict[str, types.ModuleType] = {}
    for name, rel in (
        ("modules", "modules"),
        ("modules.AgentTools", os.path.join("modules", "AgentTools")),
        ("modules.AgentRuntime", os.path.join("modules", "AgentRuntime")),
    ):
        if name not in sys.modules:
            pkg = types.ModuleType(name)
            pkg.__path__ = [os.path.join(ROOT, rel)]  # type: ignore[attr-defined]
            sys.modules[name] = pkg
            stubs[name] = pkg
    try:
        from hyperot import configurator

        if "hyper-bot" not in configurator.BotConfig._loaded_cfgs:
            configurator.BotConfig._loaded_cfgs["hyper-bot"] = configurator.BotConfig(
                protocol="OneBot",
                owner=[],
                black_list=[],
                silents=[],
                connection={"mode": "FWS", "host": "127.0.0.1", "port": 0},
                uin=0,
                others={},
            )
        module = importlib.import_module("modules.AgentTools.webpage_tools")
    finally:
        for name in stubs:
            sys.modules.pop(name, None)
    sys.modules["test_render_tools_module"] = module
    return module


RENDER = _load_render_tools()
SITE_CATCH = sys.modules["modules.site_catch"]
REGISTRY = sys.modules["modules.AgentTools.registry"]


class _FakeCatcher:
    calls: list[tuple[str, dict[str, Any]]] = []

    @classmethod
    async def init(cls) -> _FakeCatcher:
        return cls()

    async def render_html(self, html: str, **kwargs: Any) -> Any:
        type(self).calls.append((html, kwargs))
        return SITE_CATCH.RenderedHtml(png=b"\x89PNG\r\n\x1a\nrender-bytes", width=800, height=1000, truncated=True)


class RenderToolTests(unittest.IsolatedAsyncioTestCase):
    @override
    def setUp(self) -> None:
        self._patch_to_thread_sync()
        self.tools = RENDER.WebpageTools()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._patch_attr(RENDER, "RENDER_DIR", self._tmp.name)
        self._patch_attr(RENDER, "Catcher", _FakeCatcher)
        _FakeCatcher.calls.clear()

    def _patch_to_thread_sync(self) -> None:
        """测试环境的线程池完成通知不可靠,改为在当前事件循环同步执行。"""
        original = RENDER.asyncio.to_thread

        async def sync_to_thread(func: Any, /, *args: Any, **kwargs: Any) -> Any:
            return func(*args, **kwargs)

        RENDER.asyncio.to_thread = sync_to_thread  # type: ignore[assignment]
        self.addCleanup(setattr, RENDER.asyncio, "to_thread", original)

    def _patch_attr(self, module: Any, name: str, value: Any) -> None:
        original = getattr(module, name)
        setattr(module, name, value)
        self.addCleanup(setattr, module, name, original)

    async def test_registration_is_visible_to_main_and_sub_only(self) -> None:
        regs = {item.name: item for item in REGISTRY.ToolRegistry.registrations() if item.group == "render"}
        self.assertIn("render_html", regs)
        registration = regs["render_html"]
        self.assertEqual(registration.perm, "member")
        self.assertTrue(registration.main_visible)
        self.assertTrue(registration.sub_visible)
        self.assertFalse(registration.system_visible)
        self.assertIn("render_html", {item["function"]["name"] for item in REGISTRY.ToolRegistry.schema("main")})
        self.assertIn("render_html", {item["function"]["name"] for item in REGISTRY.ToolRegistry.schema("sub")})
        self.assertNotIn("render_html", {item["function"]["name"] for item in REGISTRY.ToolRegistry.schema("system")})

    async def test_render_returns_existing_png_path(self) -> None:
        result = json.loads(
            await self.tools.render_html(
                None,
                "<html><body>render</body></html>",
                width=800,
                height=600,
                full_page=True,
                wait_ms=50,
            )
        )
        path = result["file"]
        self.assertTrue(os.path.isfile(path))
        with open(path, "rb") as file:
            self.assertEqual(file.read(), b"\x89PNG\r\n\x1a\nrender-bytes")
        self.assertEqual(result["width"], 800)
        self.assertEqual(result["height"], 1000)
        self.assertTrue(result["truncated"])
        html, kwargs = _FakeCatcher.calls[0]
        self.assertEqual(html, "<html><body>render</body></html>")
        self.assertEqual(kwargs["width"], 800)
        self.assertEqual(kwargs["height"], 600)
        self.assertTrue(kwargs["full_page"])
        self.assertEqual(kwargs["wait_ms"], 50)
        self.assertIs(kwargs["request_guard"], RENDER._check_render_request)

    async def test_render_path_is_accepted_by_image_message_segment(self) -> None:
        result = json.loads(await self.tools.render_html(None, "<html><body>render</body></html>"))
        ctx = REGISTRY.ToolContext(actions=cast(Any, None), ev_type="group", scene_id=1)
        message = await ctx.create_msg([{"seg": "image", "file": result["file"]}])
        segment = next(iter(message))
        self.assertTrue(str(segment.source).startswith("file://"))

    async def test_render_argument_validation(self) -> None:
        cases = (
            (" ", 1080, 720, True, 500),
            ("x" * (RENDER.MAX_RENDER_HTML_CHARS + 1), 1080, 720, True, 500),
            ("<html/>", 100, 720, True, 500),
            ("<html/>", 1080, 100, True, 500),
            ("<html/>", 1080, 720, True, 5001),
            ("<html/>", 1080, 720, "false", 500),
        )
        for args in cases:
            with self.subTest(args=args):
                result = await self.tools.render_html(None, *args)
                self.assertTrue(result.startswith("调用不合法："), result)
        self.assertEqual(_FakeCatcher.calls, [])

    async def test_cleanup_removes_only_expired_render_files(self) -> None:
        old = os.path.join(self._tmp.name, "render_old.png")
        fresh = os.path.join(self._tmp.name, "render_fresh.png")
        other = os.path.join(self._tmp.name, "keep.txt")
        for path in (old, fresh, other):
            with open(path, "wb") as file:
                file.write(b"x")
        old_time = time.time() - RENDER.RENDER_TTL_SECONDS - 10
        os.utime(old, (old_time, old_time))
        RENDER._cleanup_rendered_files()
        self.assertFalse(os.path.exists(old))
        self.assertTrue(os.path.exists(fresh))
        self.assertTrue(os.path.exists(other))

    async def test_render_request_policy(self) -> None:
        await RENDER._check_render_request("data:text/html,<p>x</p>")
        await RENDER._check_render_request("about:blank")
        await RENDER._check_render_request("https://93.184.216.34/image.png")
        for url in ("file:///etc/passwd", "http://127.0.0.1/a.png", "ftp://example.com/a.png"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                await RENDER._check_render_request(url)

    async def test_credential_headers_are_removed(self) -> None:
        headers = SITE_CATCH._safe_request_headers(
            {
                "Cookie": "session=secret",
                "authorization": "Bearer secret",
                "Proxy-Authorization": "Basic secret",
                "User-Agent": "test",
            }
        )
        self.assertEqual(headers, {"User-Agent": "test"})

    async def test_boolean_arguments_accept_json_like_strings(self) -> None:
        self.assertIs(REGISTRY._coerce(bool, True, "flag"), True)
        self.assertIs(REGISTRY._coerce(bool, "false", "flag"), False)
        self.assertIs(REGISTRY._coerce(bool, "1", "flag"), True)
        with self.assertRaises(REGISTRY.ToolParamError):
            REGISTRY._coerce(bool, "yes", "flag")


if __name__ == "__main__":
    unittest.main()
