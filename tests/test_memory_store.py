"""MemoryStore 混合检索 / 时间窗口 / 降级路径的回归测试。"""

from __future__ import annotations

import importlib
import os
import re
import sys
import tempfile
import time
import types
import unittest
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np
from typing_extensions import override

ROOT = Path(__file__).resolve().parents[1]
STUB_DIM = 8


def _load_memory_store() -> Any:
    """与 test_api_profiles 同款方式加载 memory_store,避开 modules/__init__.py。"""
    cache_key = "test_memory_store_module"
    if cache_key in sys.modules:
        return sys.modules[cache_key]
    package_root = "test_memory_pkg"
    tools_root = "test_memory_pkg.AgentTools"
    pkg = types.ModuleType(package_root)
    pkg.__path__ = [str(ROOT / "modules")]  # type: ignore[attr-defined]
    tools = types.ModuleType(tools_root)
    tools.__path__ = [str(ROOT / "modules" / "AgentTools")]  # type: ignore[attr-defined]
    sys.modules[package_root] = pkg
    sys.modules[tools_root] = tools
    module = importlib.import_module(f"{tools_root}.memory_store")
    sys.modules[cache_key] = module
    return module


class _StubEmbedding:
    """测试替身:取第一个 ASCII 词做 one-hot,纯中文文本给零向量。

    零向量让向量臂退化成保序排列,正好用来验证 BM25 臂能在混合模式里
    把关键词命中顶到零向量条目前面。
    """

    def embed(self, texts: list[str]) -> np.ndarray:
        rows = []
        for text in texts:
            vec = np.zeros(STUB_DIM, dtype=np.float32)
            words = re.findall(r"[A-Za-z]+", text)
            if words:
                vec[sum(ord(c) for c in words[0]) % STUB_DIM] = 1.0
            rows.append(vec)
        return np.vstack(rows)


class MemoryStoreTests(unittest.TestCase):
    @override
    def setUp(self) -> None:
        self.mod = _load_memory_store()
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._seq = 0

    def _store(self, name: str, texts: list[str], timestamps: list[int] | None = None, limit: int = 100) -> Any:
        """构造带桩嵌入的 store,并按需覆写条目 ts(时间测试需要确定时间轴)。"""
        self._seq += 1
        store = self.mod.MemoryStore(os.path.join(self._tmp.name, f"{name}{self._seq}"), limit=limit)
        store._model = _StubEmbedding()
        store._bm25_only = False
        for text in texts:
            store.add(text)
        if timestamps is not None:
            for entry, ts in zip(store.entries, timestamps, strict=True):
                entry["ts"] = ts
        return store

    def test_rrf_fuse_sums_both_arms(self) -> None:
        scores = self.mod._rrf_fuse([[0, 1, 2], [2, 0, 1]])
        k = self.mod.RRF_K
        self.assertAlmostEqual(scores[0], 1 / (k + 1) + 1 / (k + 2))
        self.assertAlmostEqual(scores[1], 1 / (k + 2) + 1 / (k + 3))
        self.assertAlmostEqual(scores[2], 1 / (k + 1) + 1 / (k + 3))

    def test_time_window_extraction(self) -> None:
        mod = self.mod
        now = time.time()
        base = date.fromtimestamp(now)

        today = mod._extract_time_window("今天群里怎么样", now)
        assert today is not None
        self.assertEqual(date.fromtimestamp(today[0]), base)
        self.assertEqual(today[2], mod._TIME_WEIGHT_EXPLICIT)

        three_days = mod._extract_time_window("三天前说过的话", now)
        assert three_days is not None
        self.assertEqual(date.fromtimestamp(three_days[0]), base - timedelta(days=3))
        self.assertEqual(three_days[2], mod._TIME_WEIGHT_EXPLICIT)

        last_week = mod._extract_time_window("上周聊了什么", now)
        assert last_week is not None
        monday = base - timedelta(days=base.weekday() + 7)
        self.assertEqual(date.fromtimestamp(last_week[0]), monday)
        self.assertEqual(date.fromtimestamp(last_week[1]), monday + timedelta(days=6))

        absolute = mod._extract_time_window("8月23日定的规矩", now)
        assert absolute is not None
        self.assertEqual((date.fromtimestamp(absolute[0]).month, date.fromtimestamp(absolute[0]).day), (8, 23))

        iso = mod._extract_time_window("2024-01-05发生的事", now)
        assert iso is not None
        self.assertEqual(date.fromtimestamp(iso[0]), date(2024, 1, 5))

        vague = mod._extract_time_window("之前主人说过", now)
        assert vague is not None
        self.assertEqual(vague[2], mod._TIME_WEIGHT_VAGUE)
        self.assertGreater((vague[1] - vague[0]) / 86400, 170)

        self.assertIsNone(mod._extract_time_window("一条没有时间表达的查询", now))

    def test_keyword_hit_outranks_zero_vector_order(self) -> None:
        # 桩嵌入对纯中文文本给零向量,向量臂只剩保序;关键词命中必须赢
        store = self._store("hybrid", ["零号条目", "一号条目", "禁止刷屏的群规"])
        results = store.query_entries("刷屏 群规", top_k=3)
        self.assertEqual(results[0][0]["text"], "禁止刷屏的群规")
        # 向量臂对零向量文本是保序排名,所有条目都会进池;关键词命中必须排第一
        self.assertEqual(len(results), 3)

    def test_time_window_boost_flips_ranking(self) -> None:
        now = time.time()
        start, end, _weight, time_only = self.mod._extract_time_window("上周 群规", now)
        self.assertFalse(time_only)
        in_ts = int((start + end) / 2)
        out_ts = int(now) - 400 * 86400
        store = self._store(
            "boost",
            ["这周里聊过的事情", "很久以前定下的群规"],
            [in_ts, out_ts],
        )
        # 无加权时"群规"关键词全拿分排第一;窗口内旧条目 ×2 后反超
        results = store.query_entries("上周 群规", top_k=2)
        self.assertEqual([entry["text"] for entry, _ in results], ["这周里聊过的事情", "很久以前定下的群规"])

    def test_time_only_query_returns_window_by_recency(self) -> None:
        now = time.time()
        start, end, _weight, time_only = self.mod._extract_time_window("上周", now)
        self.assertTrue(time_only)
        in_ts = int((start + end) / 2)
        store = self._store(
            "puretime",
            ["窗口内的新记录", "窗口内的旧记录", "很久以前的记录"],
            [in_ts, in_ts - 86400, int(now) - 400 * 86400],
        )
        results = store.query_entries("上周", top_k=5)
        self.assertEqual([entry["text"] for entry, _ in results], ["窗口内的新记录", "窗口内的旧记录"])

    def test_bm25_only_mode_when_vectors_missing(self) -> None:
        store = self._store("degraded", ["主人口味:喜欢奶茶", "群规:禁止刷屏"])
        store.vecs = None
        results = store.query("群规", top_k=2)
        self.assertEqual(results[0][0], "群规:禁止刷屏")

    def test_add_dedup_limit_and_persist(self) -> None:
        store = self._store("persist", ["第一条", "第二条", "第三条"], limit=2)
        self.assertEqual(store.count(), 2)
        self.assertEqual(store.entries[0]["text"], "第二条")
        self.assertEqual(store.add("第二条"), store.entries[0]["id"])
        path = os.path.join(self._tmp.name, f"persist{self._seq}")
        reloaded = self.mod.MemoryStore(path, limit=2)
        self.assertEqual([entry["text"] for entry in reloaded.entries], ["第二条", "第三条"])


if __name__ == "__main__":
    unittest.main()
