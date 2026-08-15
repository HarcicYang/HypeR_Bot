"""RAG 长期记忆存储:本地 BGE embedding 向量检索 + BM25 降级。

存储(路径由调用方传入,不带扩展名):
- {path}.json —— 条目 [{id, text, ts}]
- {path}.npz   —— 向量矩阵 float32 (N, 512),行序与条目一一对应(已 L2 归一化)

模型:fastembed(ONNX)+ BAAI/bge-small-zh-v1.5,首次使用自动下载。
模型不可用时降级为 BM25(jieba 分词 + IDF 加权),功能不中断。

线程安全:add/delete 用模块级锁保护;embedding 是阻塞调用,调用方应
用 asyncio.to_thread 包裹。
"""

import json
import math
import os
import threading
import time
from operator import itemgetter
from typing import Any

import numpy as np

try:
    import jieba
except ImportError:  # pragma: no cover
    jieba = None

MODEL_NAME = "BAAI/bge-small-zh-v1.5"
DIM = 512

_LOCK = threading.Lock()


class MemoryStore:
    def __init__(self, path: str, limit: int = 500) -> None:
        self.path = path  # 不带扩展名;json/npz 由它派生
        self.limit = max(1, limit)
        self.entries: list[dict[str, Any]] = []
        self.vecs: np.ndarray | None = None  # (N, DIM) float32,已归一化
        self._model: Any = None
        self._bm25_only = False
        self._next_id = 1
        self._load()

    # ------------------------------------------------------------------ #
    # 持久化
    # ------------------------------------------------------------------ #

    def _json_path(self) -> str:
        return self.path + ".json"

    def _npz_path(self) -> str:
        return self.path + ".npz"

    def _load(self) -> None:
        try:
            with open(self._json_path(), encoding="utf-8") as f:
                self.entries = json.load(f)
            if not isinstance(self.entries, list):
                raise ValueError("entries 非列表")
            self.entries = [e for e in self.entries if isinstance(e, dict) and "text" in e]
            self._next_id = max((int(e.get("id", 0)) for e in self.entries), default=0) + 1
            try:
                data = np.load(self._npz_path())
                vecs = data["vecs"]
                if len(vecs) == len(self.entries):
                    self.vecs = np.asarray(vecs, dtype=np.float32)
                else:
                    self.vecs = None  # 对齐失败:丢弃向量,条目保留(BM25 兜底)
            except (FileNotFoundError, KeyError, ValueError):
                self.vecs = None
        except (FileNotFoundError, ValueError, json.JSONDecodeError):
            # 损坏:备份原文件后重置为空库
            self.entries = []
            self.vecs = None
            try:
                if os.path.exists(self._json_path()):
                    os.replace(self._json_path(), self._json_path() + ".bak")
            except OSError:
                pass

    def _persist(self) -> None:
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp_json = self._json_path() + ".tmp"
        with open(tmp_json, "w", encoding="utf-8") as f:
            json.dump(self.entries, f, indent=2, ensure_ascii=False)
        os.replace(tmp_json, self._json_path())
        if self.vecs is not None and len(self.vecs) == len(self.entries):
            tmp_npz = self._npz_path() + ".tmp"
            with open(tmp_npz, "wb") as f:
                np.savez(f, vecs=self.vecs)  # 传文件对象避免 np.savez 自动追加 .npz 扩展名
            os.replace(tmp_npz, self._npz_path())

    # ------------------------------------------------------------------ #
    # 模型
    # ------------------------------------------------------------------ #

    def _ensure_model(self) -> bool:
        """懒加载 fastembed;失败置 BM25 降级。返回是否可用向量。"""
        if self._model is not None:
            return True
        if self._bm25_only:
            return False
        try:
            from fastembed import TextEmbedding

            self._model = TextEmbedding(MODEL_NAME)
            list(self._model.embed(["预热"]))  # 触发模型下载/加载
            return True
        except Exception:
            self._model = None
            self._bm25_only = True
            return False

    def _embed(self, texts: list[str]) -> np.ndarray | None:
        """批量嵌入并 L2 归一化;失败返回 None。"""
        if not self._ensure_model():
            return None
        try:
            vecs = np.vstack(list(self._model.embed(texts)))
            norms = np.linalg.norm(vecs, axis=1, keepdims=True)
            norms[norms == 0] = 1
            return (vecs / norms).astype(np.float32)
        except Exception:
            self._bm25_only = True
            return None

    # ------------------------------------------------------------------ #
    # 检索
    # ------------------------------------------------------------------ #

    def _bm25_query(self, query: str, top_k: int) -> list[tuple[str, float]]:
        """简化 BM25:jieba 分词 + IDF 加权词频(向量不可用时的降级)。"""
        if jieba is None or not self.entries:
            return []
        try:
            q_tokens = set(jieba.lcut(query))
            if not q_tokens:
                return []
            n = len(self.entries)
            docs = [set(jieba.lcut(e["text"])) for e in self.entries]
            idf = {t: math.log(1 + n / (1 + sum(t in d for d in docs))) for t in q_tokens}
            scored: list[tuple[str, float]] = []
            for e, d in zip(self.entries, docs, strict=True):
                s = sum(idf.get(t, 0.0) for t in q_tokens if t in d)
                if s > 0:
                    scored.append((e["text"], s))
            scored.sort(key=itemgetter(1), reverse=True)
            return scored[:top_k]
        except Exception:
            return []

    def query(self, text: str, top_k: int = 5) -> list[tuple[str, float]]:
        """语义检索 top-k,返回 [(text, score)];向量不可用时降级 BM25。"""
        top_k = max(1, top_k)
        if not self.entries:
            return []
        if self.vecs is not None and len(self.vecs) == len(self.entries):
            qv = self._embed([text])
            if qv is not None:
                scores = self.vecs @ qv[0]
                idx = np.argsort(-scores)[:top_k]
                return [(self.entries[i]["text"], float(scores[i])) for i in idx]
        return self._bm25_query(text, top_k)

    # ------------------------------------------------------------------ #
    # 增删查
    # ------------------------------------------------------------------ #

    def add(self, text: str) -> int:
        """添加一条记忆(重复文本直接返回原 id),返回条目 id。"""
        text = text.strip()
        if not text:
            raise ValueError("记忆内容不能为空")
        with _LOCK:
            for e in self.entries:
                if e["text"] == text:
                    return int(e["id"])
            vec = self._embed([text])
            mem_id = self._next_id
            self._next_id += 1
            self.entries.append({"id": mem_id, "text": text[:500], "ts": int(time.time())})
            if vec is not None:
                self.vecs = vec if self.vecs is None else np.vstack([self.vecs, vec])
            while len(self.entries) > self.limit:
                self.entries.pop(0)
                if self.vecs is not None:
                    self.vecs = self.vecs[1:]
            self._persist()
            return mem_id

    def delete(self, mem_id: int) -> bool:
        """删除指定 id 的记忆,返回是否删除成功。"""
        with _LOCK:
            for i, e in enumerate(self.entries):
                if int(e.get("id", -1)) == mem_id:
                    self.entries.pop(i)
                    if self.vecs is not None:
                        self.vecs = np.delete(self.vecs, i, axis=0)
                    self._persist()
                    return True
            return False

    def list_all(self, limit: int = 20) -> list[dict[str, Any]]:
        return [dict(e) for e in self.entries[-max(1, limit) :]]

    def count(self) -> int:
        return len(self.entries)

    def is_ready(self) -> bool:
        """向量模型是否可用(False = 当前是 BM25 降级)。"""
        return self._model is not None and not self._bm25_only
