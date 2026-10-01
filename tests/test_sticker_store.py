"""StickerStore 收藏/去重/删除/淘汰/检索与 describe 降级路径的回归测试。"""

from __future__ import annotations

import asyncio
import importlib
import os
import sys
import tempfile
import types
import unittest
from typing import Any

from typing_extensions import override

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_sticker_store() -> Any:
    """加载 sticker_store,但用桩包顶替 modules / modules.AgentTools / modules.AgentRuntime,
    避免执行 modules/__init__.py(它会导入全部 bot 模块)。"""
    if "test_sticker_store_module" in sys.modules:
        return sys.modules["test_sticker_store_module"]
    _ensure_stub_config()
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
        module = importlib.import_module("modules.AgentRuntime.sticker_store")
    finally:
        for name in stubs:
            sys.modules.pop(name, None)
    sys.modules["test_sticker_store_module"] = module
    return module


def _ensure_stub_config() -> None:
    """sticker_store 在 import 时读取 configurator.BotConfig.get("hyper-bot");
    测试环境没有 main.py 的 load_from,这里注入一个最小桩配置(与生产同键同型)。"""
    from hyperot import configurator

    if "hyper-bot" in configurator.BotConfig._loaded_cfgs:
        return
    configurator.BotConfig._loaded_cfgs["hyper-bot"] = configurator.BotConfig(
        protocol="OneBot",
        owner=[],
        black_list=[],
        silents=[],
        connection={"mode": "FWS", "host": "127.0.0.1", "port": 0},
        uin=0,
        others={},
    )


class _StubEmbedding:
    """与 test_memory_store 同款:取第一个 ASCII 词做 one-hot,纯中文给零向量。"""

    def __init__(self, dim: int = 8) -> None:
        self.dim = dim

    def embed(self, texts: list[str]) -> Any:
        import re

        import numpy as np

        rows = []
        for text in texts:
            vec = np.zeros(self.dim, dtype=np.float32)
            words = re.findall(r"[A-Za-z]+", text)
            if words:
                vec[sum(ord(c) for c in words[0]) % self.dim] = 1.0
            rows.append(vec)
        return np.vstack(rows)


def _png_bytes(seed: bytes) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + seed


class StickerStoreTests(unittest.TestCase):
    @override
    def setUp(self) -> None:
        self.mod = _load_sticker_store()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._seq = 0

    def _store(self, name: str, limit: int = 100) -> Any:
        self._seq += 1
        store = self.mod.StickerStore(os.path.join(self._tmp.name, f"{name}{self._seq}"), limit=limit)
        store._model = _StubEmbedding()
        store._bm25_only = False
        return store

    def test_add_sticker_writes_file_and_entry(self) -> None:
        store = self._store("add")
        raw = _png_bytes(b"stk-one")
        entry = store.add_sticker(raw, "一只猫猫震惊的表情", keywords="震惊 猫猫", adder=10001)
        self.assertTrue(entry)
        self.assertEqual(entry["desc"], "一只猫猫震惊的表情")
        self.assertEqual(entry["adder"], 10001)
        self.assertIn("md5", entry)
        file_path = str(entry["file"])
        self.assertTrue(os.path.isfile(file_path))
        self.assertTrue(file_path.startswith(store.files_dir))
        with open(file_path, "rb") as f:
            self.assertEqual(f.read(), raw)
        self.assertEqual(store.count(), 1)

    def test_same_image_dedupes_across_reload(self) -> None:
        store = self._store("dedupe")
        raw = _png_bytes(b"stk-dup")
        first = store.add_sticker(raw, "摆烂的企鹅")
        again = store.add_sticker(raw, "摆烂的企鹅")
        self.assertEqual(first["id"], again["id"])
        self.assertEqual(store.count(), 1)
        # 重新加载:entry 的额外字段(file/md5)必须原样保留,find_by_md5 依然命中
        reloaded = self.mod.StickerStore(store.path, limit=store.limit)
        found = reloaded.find_by_md5(raw)
        self.assertIsNotNone(found)
        assert found is not None
        self.assertEqual(found["id"], first["id"])
        self.assertTrue(os.path.isfile(str(found["file"])))
        self.assertEqual(reloaded.count(), 1)

    def test_delete_sticker_removes_file(self) -> None:
        store = self._store("del")
        entry = store.add_sticker(_png_bytes(b"stk-del"), "无语的柴犬")
        file_path = str(entry["file"])
        removed = store.delete_sticker(int(entry["id"]))
        self.assertEqual(removed, entry)
        self.assertFalse(os.path.exists(file_path))
        self.assertEqual(store.count(), 0)
        self.assertIsNone(store.delete_sticker(int(entry["id"])))
        self.assertIsNone(store.delete_sticker(999))

    def test_limit_evicts_oldest_and_unlinks_file(self) -> None:
        store = self._store("evict", limit=2)
        first = store.add_sticker(_png_bytes(b"stk-1"), "第一张表情")
        second = store.add_sticker(_png_bytes(b"stk-2"), "第二张表情")
        store.add_sticker(_png_bytes(b"stk-3"), "第三张表情")
        self.assertEqual(store.count(), 2)
        self.assertFalse(os.path.exists(str(first["file"])))
        self.assertTrue(os.path.isfile(str(second["file"])))
        self.assertEqual([e["desc"] for e in store.entries], ["第二张表情", "第三张表情"])

    def test_search_returns_sticker_entries(self) -> None:
        store = self._store("search")
        store.add_sticker(_png_bytes(b"stk-a"), "猫咪双手捂脸露出震惊表情", keywords="震惊")
        store.add_sticker(_png_bytes(b"stk-b"), "熊猫躺平摆烂一脸生无可恋", keywords="摆烂")
        results = store.search("震惊 猫猫", top_k=5)
        self.assertTrue(results)
        self.assertIn("震惊", str(results[0]["desc"]))
        self.assertTrue(os.path.isfile(str(results[0]["file"])))
        self.assertIn("score", results[0])
        # list_recent 为收藏时间倒序
        self.assertEqual(
            [e["desc"] for e in store.list_recent(5)], ["熊猫躺平摆烂一脸生无可恋", "猫咪双手捂脸露出震惊表情"]
        )

    def test_index_text_is_unique_per_image(self) -> None:
        text_a = self.mod._index_text("崩溃", "同一样的描述", "a" * 32)
        text_b = self.mod._index_text("崩溃", "同一样的描述", "b" * 32)
        self.assertNotEqual(text_a, text_b)
        long_text = self.mod._index_text("关键词" * 100, "描述" * 100, "c" * 32)
        self.assertLessEqual(len(long_text), self.mod.INDEX_TEXT_MAX)
        self.assertTrue(long_text.endswith("[stk:cccccccc]"))

    def test_describe_returns_empty_without_key_or_on_error(self) -> None:
        config = self.mod.config
        original = config.others.get("gemini_key")
        config.others["gemini_key"] = ""
        try:
            self.assertEqual(asyncio.run(self.mod.describe_sticker_image(b"no-key")), "")
        finally:
            if original is None:
                config.others.pop("gemini_key", None)
            else:
                config.others["gemini_key"] = original

        config.others["gemini_key"] = "fake-key"
        saved = {key: sys.modules.get(key) for key in ("google", "google.genai")}
        try:
            google_pkg = types.ModuleType("google")
            genai_mod = types.ModuleType("google.genai")

            class _BrokenClient:
                def __init__(self, **kwargs: Any) -> None:
                    pass

                @property
                def models(self) -> Any:
                    raise RuntimeError("vision unavailable")

            genai_mod.Client = _BrokenClient  # type: ignore[attr-defined]
            genai_mod.types = types.SimpleNamespace(  # type: ignore[attr-defined]
                Part=types.SimpleNamespace(from_bytes=lambda **kw: None, from_text=lambda **kw: None)
            )
            google_pkg.genai = genai_mod  # type: ignore[attr-defined]
            sys.modules["google"] = google_pkg
            sys.modules["google.genai"] = genai_mod
            # 调用失败必须静默降级为空串,由命令侧退化为用户关键词
            self.assertEqual(asyncio.run(self.mod.describe_sticker_image(b"boom")), "")
        finally:
            config.others.pop("gemini_key", None)
            if original is not None:
                config.others["gemini_key"] = original
            for key, value in saved.items():
                if value is None:
                    sys.modules.pop(key, None)
                else:
                    sys.modules[key] = value


if __name__ == "__main__":
    unittest.main()
