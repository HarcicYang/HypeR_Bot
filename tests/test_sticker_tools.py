"""sticker 工具层(sticker_add / sticker_delete / search / list / send)与无权限分级的回归测试。"""

from __future__ import annotations

import asyncio
import importlib
import json
import os
import sys
import tempfile
import types
import unittest
from types import SimpleNamespace
from typing import Any

from typing_extensions import override

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_sticker_tools() -> Any:
    """加载 sticker_tools(连带 registry 与 sticker_store),绕开 modules/__init__.py。"""
    if "test_sticker_tools_module" in sys.modules:
        return sys.modules["test_sticker_tools_module"]
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
        module = importlib.import_module("modules.AgentTools.sticker_tools")
    finally:
        for name in stubs:
            sys.modules.pop(name, None)
    sys.modules["test_sticker_tools_module"] = module
    return module


class _FakeStore:
    """命令/工具测试替身:只实现 sticker 工具用到的存储面。"""

    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []
        self.deleted: list[int] = []
        self._next_id = 1

    def find_by_md5(self, raw: bytes) -> dict[str, Any] | None:
        import hashlib

        md5 = hashlib.md5(raw).hexdigest()
        return next((e for e in self.entries if e.get("md5") == md5), None)

    def add_sticker(self, raw: bytes, desc: str, keywords: str = "", adder: int = 0) -> dict[str, Any]:
        import hashlib

        entry = {
            "id": self._next_id,
            "desc": desc,
            "keywords": keywords,
            "adder": adder,
            "md5": hashlib.md5(raw).hexdigest(),
            "file": f"/tmp/fake-sticker-{self._next_id}.png",
            "ts": 0,
        }
        self._next_id += 1
        self.entries.append(entry)
        return entry

    def get(self, sticker_id: int) -> dict[str, Any] | None:
        return next((e for e in self.entries if e["id"] == sticker_id), None)

    def delete_sticker(self, sticker_id: int) -> dict[str, Any] | None:
        entry = self.get(sticker_id)
        if entry is None:
            return None
        self.entries.remove(entry)
        self.deleted.append(sticker_id)
        return entry

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        hits = [e for e in self.entries if query in str(e.get("desc") or "")]
        return [{**e, "score": 1.0} for e in hits[:top_k]]

    def list_recent(self, limit: int = 10) -> list[dict[str, Any]]:
        return list(reversed(self.entries[-max(1, limit) :]))

    def count(self) -> int:
        return len(self.entries)


class _FakeActions:
    def __init__(self) -> None:
        self.sent: list[Any] = []

    def group(self, scene_id: str) -> _FakeActions:
        return self

    def user(self, scene_id: str) -> _FakeActions:
        return self

    async def send(self, message: Any) -> Any:
        self.sent.append(message)
        return SimpleNamespace(message_id=777)


class StickerToolsTests(unittest.IsolatedAsyncioTestCase):
    @override
    def setUp(self) -> None:
        self.mod = _load_sticker_tools()
        self.store_mod = sys.modules["modules.AgentRuntime.sticker_store"]
        self.registry_mod = sys.modules["modules.AgentTools.registry"]
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.png = os.path.join(self._tmp.name, "sticker.png")
        with open(self.png, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\ntool-sticker-bytes")
        self.store = _FakeStore()
        self.describe_calls: list[str] = []
        self._patch_to_thread_sync()
        self._patch_attr(self.mod, "get_sticker_store", lambda: self.store)
        self._patch_attr(self.store_mod, "get_sticker_store", lambda: self.store)

        async def fake_describe(raw: bytes, hint: str = "") -> str:
            self.describe_calls.append(hint)
            return "一只猫猫双手捂脸,表情崩溃,配文不要啊"

        self._patch_attr(self.store_mod, "describe_sticker_image", fake_describe)
        self.mod.LAST_SENT.clear()

    def _patch_to_thread_sync(self) -> None:
        """沙箱内 asyncio 线程池执行器的完成通知到不了事件循环,换成同步执行;生产不受影响。"""
        original = asyncio.to_thread

        async def sync_to_thread(func: Any, /, *args: Any, **kwargs: Any) -> Any:
            return func(*args, **kwargs)

        asyncio.to_thread = sync_to_thread  # type: ignore[assignment]
        self.addCleanup(setattr, asyncio, "to_thread", original)

    def _patch_attr(self, module: Any, name: str, value: Any) -> None:
        original = getattr(module, name)
        setattr(module, name, value)
        self.addCleanup(setattr, module, name, original)

    def _ctx(self, perm_group: str = "member") -> Any:
        return self.registry_mod.ToolContext(
            actions=_FakeActions(),
            ev_type="group",
            scene_id=20002,
            perm_group=perm_group,
            principal_id=10001,
            self_id=30003,
        )

    def _tools(self) -> Any:
        return self.mod.StickerTools()

    def test_registration_is_permission_free(self) -> None:
        regs = {t.name: t for t in self.registry_mod.ToolRegistry.registrations() if t.group == "sticker"}
        self.assertEqual(
            sorted(regs),
            ["sticker_add", "sticker_delete", "sticker_list", "sticker_search", "sticker_send"],
        )
        for name, reg in regs.items():
            self.assertEqual(reg.perm, "member", f"{name} 不应设置权限分级")
            self.assertEqual(reg.scenes, ("group", "private"))

    async def test_dispatch_add_and_delete_as_plain_member(self) -> None:
        # 经真正的注册表分发:普通成员(member)调用 add/delete 不得被权限拦截
        ctx = self._ctx(perm_group="member")
        added = await self.registry_mod.ToolRegistry.dispatch(
            "sticker_add", {"url": "file://" + self.png, "keywords": "崩溃 猫猫"}, ctx
        )
        self.assertIn("已收藏为表情包 #1", added)
        self.assertIn("关键词:崩溃 猫猫", added)
        entry = self.store.get(1)
        assert entry is not None
        self.assertEqual(entry["adder"], 10001)

        deleted = await self.registry_mod.ToolRegistry.dispatch("sticker_delete", {"sticker_id": 1}, ctx)
        self.assertEqual(deleted, "表情包 #1 已删除")
        self.assertEqual(self.store.deleted, [1])

    async def test_sticker_add_success_duplicate_and_failure(self) -> None:
        tools = self._tools()
        ctx = self._ctx()
        text = await tools.sticker_add(ctx, "file://" + self.png, "震惊")
        self.assertIn("已收藏为表情包 #1", text)
        self.assertIn("描述:一只猫猫双手捂脸", text)
        self.assertEqual(self.describe_calls, ["震惊"])

        # 同一张图复用条目,不重复调用 Gemini
        again = await tools.sticker_add(ctx, "file://" + self.png, "再试一次")
        self.assertIn("这张图片已收藏为表情包 #1", again)
        self.assertEqual(self.describe_calls, ["震惊"])
        self.assertEqual(self.store.count(), 1)

        failed = await tools.sticker_add(ctx, "file:///nonexistent/sticker.png")
        self.assertIn("收藏失败：图片下载失败", failed)
        self.assertEqual(self.store.count(), 1)

    async def test_sticker_delete_missing(self) -> None:
        tools = self._tools()
        ctx = self._ctx()
        self.store.add_sticker(b"x", "描述X")
        self.assertEqual(await tools.sticker_delete(ctx, 1), "表情包 #1 已删除")
        missing = await tools.sticker_delete(ctx, 42)
        self.assertIn("表情包 #42 不存在", missing)

    async def test_sticker_search_and_list_return_json(self) -> None:
        tools = self._tools()
        ctx = self._ctx()
        self.store.add_sticker(b"a", "猫咪震惊", keywords="震惊")
        self.store.add_sticker(b"b", "熊猫摆烂", keywords="摆烂")
        found = json.loads(await tools.sticker_search(ctx, "震惊"))
        self.assertEqual(found["total"], 2)
        self.assertEqual(len(found["items"]), 1)
        self.assertIn("file", found["items"][0])

        listed = json.loads(await tools.sticker_list(ctx, 5))
        self.assertEqual([e["desc"] for e in listed["items"]], ["熊猫摆烂", "猫咪震惊"])

    async def test_sticker_send_and_cooldown(self) -> None:
        tools = self._tools()
        ctx = self._ctx()
        self.store.add_sticker(b"c", "猫咪震惊")
        self.store.entries[0]["file"] = self.png  # 指向真实文件
        sent = await tools.sticker_send(ctx, 1)
        self.assertIn("已发送：message_id=777", sent)
        self.assertEqual(len(ctx.actions.sent), 1)

        cooled = await tools.sticker_send(ctx, 1)
        self.assertIn("发送太频繁", cooled)
        self.assertEqual(len(ctx.actions.sent), 1)

        missing = await tools.sticker_send(ctx, 99)
        self.assertIn("不存在", missing)


if __name__ == "__main__":
    unittest.main()
