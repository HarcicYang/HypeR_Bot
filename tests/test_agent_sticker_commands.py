""".ag.stk 命令归一化/分发与参数解析的回归测试（不触网、不连 QQ）。"""

from __future__ import annotations

import importlib
import os
import sys
import tempfile
import types
import unittest
from types import SimpleNamespace
from typing import Any

from hyperot.v2 import Image, Message, SceneType, Text
from typing_extensions import override

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_agent() -> Any:
    """与 test_sticker_store 同款桩包方式加载 modules.Agent,
    绕开 modules/__init__.py(会导入全部 bot 模块)与 config.json 依赖。"""
    if "test_agent_module" in sys.modules:
        return sys.modules["test_agent_module"]
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
        module = importlib.import_module("modules.Agent")
    finally:
        for name in stubs:
            sys.modules.pop(name, None)
    sys.modules["test_agent_module"] = module
    return module


def _load_sticker_store_mod() -> Any:
    """加载 sticker_store 模块对象(命令的 collect_sticker 在其命名空间内解析 store/describe)。"""
    if "test_sticker_store_module" in sys.modules:
        return sys.modules["test_sticker_store_module"]
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
        module = importlib.import_module("modules.AgentRuntime.sticker_store")
    finally:
        for name in stubs:
            sys.modules.pop(name, None)
    sys.modules["test_sticker_store_module"] = module
    return module


def _fake_event(text: str) -> Any:
    return SimpleNamespace(
        message=Message(Text(text=text)),
        message_id=100,
        user_id=10001,
        scene_type=SceneType.GROUP,
        scene_id=20002,
        self_id=30003,
    )


class AgentStickerCommandTests(unittest.IsolatedAsyncioTestCase):
    @override
    def setUp(self) -> None:
        self.mod = _load_agent()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)

    async def _dispatch(self, text: str) -> tuple[str, list[str], str]:
        """跑 _cmd,用桩替换 _cmd_sticker,返回 (归一化后的 sub, parts, text)。"""
        agent = self.mod._Agent()
        recorded: list[tuple[str, list[str], str]] = []

        async def fake_sticker(event: Any, text: str, parts: list[str], sub: str) -> None:
            recorded.append((sub, list(parts), text))

        agent._cmd_sticker = fake_sticker  # type: ignore[method-assign]
        await agent._cmd(_fake_event(text))
        self.assertEqual(len(recorded), 1, f"{text} 未路由到表情包子命令")
        return recorded[0]

    async def test_all_command_forms_route_to_sticker(self) -> None:
        cases: dict[str, tuple[str, list[str]]] = {
            ".ag.stk add 关键词": ("sticker", ["add", "关键词"]),
            ".ag.stk.ad 关键词": ("sticker.add", ["关键词"]),
            ".ag.stk.add 关键词": ("sticker.add", ["关键词"]),
            ".agent sticker del 5": ("sticker", ["del", "5"]),
            # 长名点号形式不进简写表,原样透传;由 _cmd_sticker 的动作别名(del→remove)归一
            ".agent.sticker.del 5": ("sticker.del", ["5"]),
            ".ag.stk.rm 5": ("sticker.remove", ["5"]),
            # 点号与空格写法在归一化后同形:首 token 即 "stk.list",20 作为 limit 参数
            ".ag.stk.list 20": ("sticker.list", ["20"]),
            ".ag.stk.ls 20": ("sticker.list", ["20"]),
            ".ag.stk.in 7": ("sticker.info", ["7"]),
            ".ag.stk": ("sticker", []),
        }
        for text, (expected_sub, expected_tail) in cases.items():
            with self.subTest(text=text):
                sub, parts, normalized = await self._dispatch(text)
                self.assertEqual(sub, expected_sub)
                self.assertEqual(parts[2:], expected_tail)
                self.assertTrue(normalized.startswith(".agent "))

    def test_id_and_image_source_parsing(self) -> None:
        agent = self.mod._Agent()
        self.assertEqual(agent._sticker_id_arg([".agent", "stk", "del", "5"]), 5)
        self.assertEqual(agent._sticker_id_arg([".agent", "stk.del", "5"]), 5)
        self.assertIsNone(agent._sticker_id_arg([".agent", "stk", "del"]))
        event = SimpleNamespace(message=Message(Text(text=".ag.stk.add"), Image(source="http://example.com/1.png")))
        self.assertEqual(agent._sticker_image_sources(event), ["http://example.com/1.png"])

    def test_help_text_documents_sticker_commands(self) -> None:
        self.assertIn(".ag.stk.add [关键词]", self.mod.AGENT_HELP)
        self.assertIn(".ag.stk.del <id>", self.mod.STICKER_USAGE)


class _FakeStore:
    """命令层测试替身:只实现 .ag.stk 命令用到的存储面(真实检索由 test_sticker_store 覆盖)。"""

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

    def list_recent(self, limit: int = 10) -> list[dict[str, Any]]:
        return list(reversed(self.entries[-max(1, limit) :]))

    def count(self) -> int:
        return len(self.entries)


class AgentStickerFlowTests(unittest.IsolatedAsyncioTestCase):
    """_cmd → _cmd_sticker_* 全链路:取图、去重、Gemini 描述、入库与回复文案。

    表情包库全局共享且不设权限分级:任何用户都能添加/删除任意表情包。"""

    @override
    def setUp(self) -> None:
        self.mod = _load_agent()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        png = os.path.join(self._tmp.name, "sticker.png")
        with open(png, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\nfake-sticker-bytes")
        self.png = png
        self.store = _FakeStore()
        self.describe_calls: list[str] = []
        self.replies: list[str] = []
        self._patch_to_thread_sync()

    def _patch_to_thread_sync(self) -> None:
        """沙箱内 asyncio 线程池执行器的完成通知到不了事件循环(线程跑完但 future 不 resolve),
        这里把 to_thread 换成同步执行版本,让流程测试不依赖真实线程;生产路径不受影响。"""
        import asyncio

        original = asyncio.to_thread

        async def sync_to_thread(func: Any, /, *args: Any, **kwargs: Any) -> Any:
            return func(*args, **kwargs)

        asyncio.to_thread = sync_to_thread  # type: ignore[assignment]
        self.addCleanup(setattr, asyncio, "to_thread", original)

    def _patch_attr(self, module: Any, name: str, value: Any) -> None:
        """补模块属性并在测试后恢复,避免污染同一进程内的其他测试文件。"""
        original = getattr(module, name)
        setattr(module, name, value)
        self.addCleanup(setattr, module, name, original)

    def _agent(self) -> Any:
        agent = self.mod._Agent()

        async def fake_describe(raw: bytes, hint: str = "") -> str:
            self.describe_calls.append(hint)
            return "一只猫猫双手捂脸,表情崩溃,配文不要啊"

        async def capture_reply(event: Any, text: str) -> None:
            self.replies.append(text)

        # 命令经 sticker_store.collect_sticker 编排,store/describe 都在该模块命名空间内解析
        store_mod = _load_sticker_store_mod()
        self._patch_attr(self.mod, "get_sticker_store", lambda: self.store)
        self._patch_attr(store_mod, "get_sticker_store", lambda: self.store)
        self._patch_attr(store_mod, "describe_sticker_image", fake_describe)
        self._patch_attr(agent, "_reply", capture_reply)
        return agent

    def _event(self, text: str, with_image: bool = True) -> Any:
        segs: list[Any] = [Text(text=text)]
        if with_image:
            segs.append(Image(source="file://" + self.png))
        return SimpleNamespace(
            message=Message(*segs),
            message_id=100,
            user_id=10001,
            scene_type=SceneType.GROUP,
            scene_id=20002,
            self_id=30003,
        )

    def _write_png(self, name: str, payload: bytes) -> str:
        path = os.path.join(self._tmp.name, name)
        with open(path, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n" + payload)
        return path

    async def test_add_describes_and_stores_sticker(self) -> None:
        agent = self._agent()
        await agent._cmd(self._event(".ag.stk.add 崩溃 猫猫"))
        self.assertEqual(len(self.replies), 1)
        self.assertIn("已收藏为表情包 #1", self.replies[0])
        self.assertIn("一只猫猫双手捂脸", self.replies[0])
        self.assertIn("关键词:崩溃 猫猫", self.replies[0])  # [图片] 占位符不得混入关键词
        self.assertEqual(self.describe_calls, ["崩溃 猫猫"])
        entry = self.store.get(1)
        assert entry is not None
        self.assertEqual(entry["adder"], 10001)
        self.assertEqual(entry["keywords"], "崩溃 猫猫")

        # 空格写法(.ag.stk add)同样拿到完整关键词,且是另一张图
        other = self._write_png("sticker2.png", b"another-sticker")
        event = self._event(".ag.stk add 摆烂 熊猫")
        event.message = Message(Text(text=".ag.stk add 摆烂 熊猫"), Image(source="file://" + other))
        await agent._cmd(event)
        self.assertEqual(self.store.count(), 2)
        second = self.store.get(2)
        assert second is not None
        self.assertEqual(second["keywords"], "摆烂 熊猫")
        self.assertIn("关键词:摆烂 熊猫", self.replies[-1])

    async def test_add_same_image_reuses_entry_without_describe(self) -> None:
        agent = self._agent()
        await agent._cmd(self._event(".ag.stk.add 第一次"))
        await agent._cmd(self._event(".ag.stk.add 第二次"))
        self.assertEqual(self.store.count(), 1)
        self.assertEqual(len(self.describe_calls), 1)
        self.assertIn("这张图片已收藏为表情包 #1", self.replies[-1])

    async def test_add_without_image_is_rejected(self) -> None:
        agent = self._agent()
        await agent._cmd(self._event(".ag.stk.add 没有图", with_image=False))
        self.assertIn("请带上要收藏的图片", self.replies[-1])

    async def test_delete_own_sticker_allowed(self) -> None:
        agent = self._agent()
        self.store.add_sticker(b"a", "描述A", adder=10001)
        await agent._cmd(self._event(".ag.stk.del 1", with_image=False))
        self.assertEqual(self.store.deleted, [1])
        self.assertIn("表情包 #1 已删除", self.replies[-1])

    async def test_delete_any_sticker_allowed(self) -> None:
        # 全局库不区分用户:普通成员(uid 10001,非白名单/管理员)也能删别人收藏的表情包
        agent = self._agent()
        self.store.add_sticker(b"b", "描述B", adder=999)
        await agent._cmd(self._event(".ag.stk.del 1", with_image=False))
        self.assertEqual(self.store.deleted, [1])
        self.assertIn("表情包 #1 已删除", self.replies[-1])

    async def test_delete_missing_sticker_reports_not_found(self) -> None:
        agent = self._agent()
        await agent._cmd(self._event(".ag.stk.del 7", with_image=False))
        self.assertIn("表情包 #7 不存在", self.replies[-1])

    async def test_list_and_info(self) -> None:
        agent = self._agent()
        self.store.add_sticker(b"c", "猫咪震惊", keywords="震惊", adder=10001)
        self.store.add_sticker(b"d", "熊猫摆烂", keywords="摆烂", adder=10002)
        await agent._cmd(self._event(".ag.stk.list", with_image=False))
        self.assertIn("表情包库共 2 张", self.replies[-1])
        self.assertIn("#2 [摆烂] 熊猫摆烂", self.replies[-1])

        await agent._cmd(self._event(".ag.stk.info 1", with_image=False))
        self.assertIn("描述:猫咪震惊", self.replies[-1])
        self.assertIn("收藏者:10001", self.replies[-1])


if __name__ == "__main__":
    unittest.main()
