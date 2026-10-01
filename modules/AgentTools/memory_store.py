"""RAG 长期记忆存储:本地 BGE embedding 向量检索 + BM25 降级。

存储(路径由调用方传入,不带扩展名):
- {path}.json —— 条目 [{id, text, ts}]
- {path}.npz   —— 向量矩阵 float32 (N, 512),行序与条目一一对应(已 L2 归一化)

模型:fastembed(ONNX)+ BAAI/bge-small-zh-v1.5,首次使用自动下载。
模型不可用时降级为 BM25(jieba 分词 + IDF 加权),功能不中断。

线程安全:add/delete 用模块级锁保护;embedding 是阻塞调用,调用方应
用 asyncio.to_thread 包裹。
"""

import calendar
import json
import logging
import math
import os
import re
import threading
import time
from datetime import date, datetime, timedelta
from typing import Any

import numpy as np

try:
    import jieba
except ImportError:  # pragma: no cover
    jieba = None

MODEL_NAME = "BAAI/bge-small-zh-v1.5"
DIM = 512

_LOCK = threading.Lock()
_LOGGER = logging.getLogger(__name__)


RRF_K = 60  # RRF 融合阻尼常数
_TIME_WEIGHT_EXPLICIT = 1.0  # 显式时间窗口(上周/三天前/8月23日)的加权强度
_TIME_WEIGHT_VAGUE = 0.5  # 模糊回溯(之前/上次)的软窗口,加权更轻
_VAGUE_WINDOW_DAYS = 180  # 模糊回溯软窗口长度(天)

_CN_DIGITS = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_NUM = r"(\d+|[零一二两三四五六七八九十]+)"
_VAGUE_RE = re.compile(r"之前|以前|曾经|上次|当时|早前|早些")
_PARTICLE_RE = re.compile(r"[\s,，。.?？!！~～、的吧啊呀哎哦嘛嗯]")


def _cn_number(text: str) -> int | None:
    """解析 "三/十五/二十" 这类中文数字(到九十九为止),失败返回 None。"""
    if not text:
        return None
    if text == "十":
        return 10
    if "十" in text:
        left, _, right = text.partition("十")
        if (left and left not in _CN_DIGITS) or (right and right not in _CN_DIGITS):
            return None
        tens = _CN_DIGITS[left] if left else 1
        ones = _CN_DIGITS[right] if right else 0
        return tens * 10 + ones
    if len(text) == 1 and text in _CN_DIGITS:
        return _CN_DIGITS[text]
    return None


def _num_value(text: str) -> int | None:
    """阿拉伯数字或中文数字转 int,无法解析返回 None。"""
    if text.isdigit():
        return int(text)
    return _cn_number(text)


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _day_start(day: date) -> int:
    return int(datetime.combine(day, datetime.min.time()).timestamp())


def _day_end(day: date) -> int:
    return int(datetime.combine(day, datetime.max.time()).timestamp())


def _day_bounds(day: date) -> tuple[int, int]:
    return _day_start(day), _day_end(day)


def _last_n_days_window(base: date, days: int, now: float) -> tuple[int, int]:
    """最近 N 天(含今天)的窗口。"""
    return _day_start(base - timedelta(days=max(1, days) - 1)), int(now)


def _week_window(base: date, weeks_back: int) -> tuple[int, int]:
    """以周一为起点的自然周窗口;weeks_back=0 为本周,1 为上周。"""
    monday = base - timedelta(days=base.weekday() + 7 * weeks_back)
    return _day_start(monday), _day_end(monday + timedelta(days=6))


def _month_window(base: date, months_back: int) -> tuple[int, int]:
    """自然月窗口;months_back=0 为本月,1 为上月,"N 个月前" 即 N 个月前的整月。"""
    total = base.year * 12 + (base.month - 1) - months_back
    year, month_index = divmod(total, 12)
    first = date(year, month_index + 1, 1)
    last = date(year, month_index + 1, calendar.monthrange(year, month_index + 1)[1])
    return _day_start(first), _day_end(last)


def _year_window(year: int) -> tuple[int, int]:
    return _day_start(date(year, 1, 1)), _day_end(date(year, 12, 31))


def _rrf_fuse(arms: list[list[int]]) -> dict[int, float]:
    """RRF 融合多个排名臂:score = Σ 1/(k + rank + 1)。"""
    scores: dict[int, float] = {}
    for arm in arms:
        for rank, idx in enumerate(arm):
            scores[idx] = scores.get(idx, 0.0) + 1.0 / (RRF_K + rank + 1)
    return scores


def _score_rank_key(item: tuple[int, float]) -> tuple[float, int]:
    """(下标, 分数) 的排序键:分数降序,同分按下标升序保稳定。"""
    return -item[1], item[0]


def _match_window(query: str, now: float) -> tuple[tuple[int, int], float, re.Match[str]] | None:
    """按优先级匹配查询中的时间表达,返回 ((start, end), weight, match)。"""
    base = date.fromtimestamp(now)

    # 绝对日期:2026-08-23 / 2026年8月23日 / 8月23日 / 8/23
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", query) or re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})[日号]?", query)
    if m:
        day = _safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return None if day is None else (_day_bounds(day), _TIME_WEIGHT_EXPLICIT, m)
    m = re.search(r"(?<!\d)(\d{1,2})月(\d{1,2})[日号]?(?!\d)", query) or re.search(
        r"(?<!\d)(\d{1,2})/(\d{1,2})(?!\d)", query
    )
    if m:
        month, day_number = int(m.group(1)), int(m.group(2))
        day = _safe_date(base.year, month, day_number)
        if day is not None and day > base + timedelta(days=1):
            day = _safe_date(base.year - 1, month, day_number)  # 记忆在过去,未来的月日归到去年
        return None if day is None else (_day_bounds(day), _TIME_WEIGHT_EXPLICIT, m)

    # 带数量的相对表达(三天前/两周前/三个月前/半小时前)
    m = re.search(_NUM + r"\s*天前", query)
    if m and (n := _num_value(m.group(1))) is not None and n > 0:
        return _day_bounds(base - timedelta(days=n)), _TIME_WEIGHT_EXPLICIT, m
    m = re.search(_NUM + r"\s*个?(?:星期|周)前", query)
    if m and (n := _num_value(m.group(1))) is not None and n > 0:
        return _week_window(base, n), _TIME_WEIGHT_EXPLICIT, m
    m = re.search(_NUM + r"\s*个?月前", query)
    if m and (n := _num_value(m.group(1))) is not None and n > 0:
        return _month_window(base, n), _TIME_WEIGHT_EXPLICIT, m
    m = re.search("半年", query)
    if m:
        return _month_window(base, 6), _TIME_WEIGHT_EXPLICIT, m
    m = re.search("半小时", query)
    if m:
        return _day_bounds(base), _TIME_WEIGHT_EXPLICIT, m
    m = re.search("去年", query)
    if m:
        return _year_window(base.year - 1), _TIME_WEIGHT_EXPLICIT, m
    m = re.search("前年", query)
    if m:
        return _year_window(base.year - 2), _TIME_WEIGHT_EXPLICIT, m

    # 自然周/月
    m = re.search(r"上周|上星期", query)
    if m:
        return _week_window(base, 1), _TIME_WEIGHT_EXPLICIT, m
    m = re.search(r"这周|本周|这星期|本星期|一周", query)
    if m:
        return _week_window(base, 0), _TIME_WEIGHT_EXPLICIT, m
    m = re.search(r"上月|上个月", query)
    if m:
        return _month_window(base, 1), _TIME_WEIGHT_EXPLICIT, m
    m = re.search(r"这个月|本月|当月", query)
    if m:
        return _month_window(base, 0), _TIME_WEIGHT_EXPLICIT, m

    # 具体某天(大前天必须在前天之前判断,否则会被 "前天" 抢先匹配)
    m = re.search(r"今天早上|今天上午|今天下午|今天晚上|今天|今日", query)
    if m:
        return _day_bounds(base), _TIME_WEIGHT_EXPLICIT, m
    m = re.search("大前天", query)
    if m:
        return _day_bounds(base - timedelta(days=3)), _TIME_WEIGHT_EXPLICIT, m
    m = re.search("前天", query)
    if m:
        return _day_bounds(base - timedelta(days=2)), _TIME_WEIGHT_EXPLICIT, m
    m = re.search(r"昨天|昨日|昨晚", query)
    if m:
        return _day_bounds(base - timedelta(days=1)), _TIME_WEIGHT_EXPLICIT, m

    # 区间表达
    m = re.search(r"(?:最近|近|过去)\s*" + _NUM + r"\s*天", query)
    if m and (n := _num_value(m.group(1))) is not None and n > 0:
        return _last_n_days_window(base, n, now), _TIME_WEIGHT_EXPLICIT, m
    m = re.search("前几天", query)
    if m:
        return _last_n_days_window(base, 7, now), _TIME_WEIGHT_EXPLICIT, m
    m = re.search(r"前阵子|前一段时间|前段时间", query)
    if m:
        return _last_n_days_window(base, 30, now), _TIME_WEIGHT_EXPLICIT, m

    # 模糊回溯:无锚点,软窗口 + 低权重
    m = _VAGUE_RE.search(query)
    if m:
        return _last_n_days_window(base, _VAGUE_WINDOW_DAYS, now), _TIME_WEIGHT_VAGUE, m
    return None


def _extract_time_window(query: str, now: float) -> tuple[int, int, float, bool] | None:
    """解析查询中的时间表达,返回 (start_ts, end_ts, weight, time_only);无则 None。

    time_only=True 表示去掉时间词后查询几乎不剩内容,调用方可跳过检索臂,
    直接按窗口内时间倒序返回。窗口只加权不过滤:窗口内命中分数 ×(1+weight)。
    """
    found = _match_window(query, now)
    if found is None:
        return None
    (start, end), weight, match = found
    residual = _PARTICLE_RE.sub("", query[: match.start()] + query[match.end() :])
    return start, end, weight, len(residual) <= 1


class MemoryStore:
    def __init__(self, path: str, limit: int = 500) -> None:
        self.path = path  # 不带扩展名;json/npz 由它派生
        self.limit = max(1, limit)
        self.entries: list[dict[str, Any]] = []
        self.vecs: np.ndarray | None = None  # (N, DIM) float32,已归一化
        self._model: Any = None
        self._bm25_only = False
        self._next_id = 1
        self._mutations = 0  # entries 变更计数,驱动分词缓存失效
        self._token_cache: tuple[int, list[set[str]]] | None = None
        self._load()
        self._mutations += 1

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
        except Exception as e:
            self._model = None
            self._bm25_only = True
            _LOGGER.warning("fastembed model unavailable; falling back to BM25: %r", e)
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
        except Exception as e:
            self._bm25_only = True
            _LOGGER.warning("fastembed embedding failed; falling back to BM25: %r", e)
            return None

    # ------------------------------------------------------------------ #
    # 检索(向量 + BM25 双臂 RRF 融合,时间窗口加权)
    # ------------------------------------------------------------------ #

    def _doc_tokens(self) -> list[set[str]]:
        """jieba 分词缓存;entries 增删后按 _mutations 自动失效重建。"""
        if jieba is None or not self.entries:
            return []
        if self._token_cache is not None and self._token_cache[0] == self._mutations:
            return self._token_cache[1]
        docs = [set(jieba.lcut(e["text"])) for e in self.entries]
        self._token_cache = (self._mutations, docs)
        return docs

    def _vector_ranking(self, text: str) -> list[int] | None:
        """向量臂:查询嵌入与全部条目求余弦,返回下标降序排名;向量不可用时 None。"""
        if self.vecs is None or len(self.vecs) != len(self.entries):
            return None
        qv = self._embed([text])
        if qv is None:
            return None
        scores = self.vecs @ qv[0]
        return [int(i) for i in np.argsort(-scores, kind="stable")]

    def _bm25_ranking(self, query: str) -> list[int]:
        """BM25 臂:jieba 分词 + IDF 加权词频,返回下标降序排名(不再只是降级兜底)。"""
        if jieba is None or not self.entries:
            return []
        try:
            q_tokens = set(jieba.lcut(query))
            if not q_tokens:
                return []
            n = len(self.entries)
            docs = self._doc_tokens()
            idf = {t: math.log(1 + n / (1 + sum(t in d for d in docs))) for t in q_tokens}
            scored: list[tuple[int, float]] = []
            for i, d in enumerate(docs):
                s = sum(idf[t] for t in q_tokens if t in d)
                if s > 0:
                    scored.append((i, s))
            scored.sort(key=_score_rank_key)
            return [i for i, _ in scored]
        except Exception:
            return []

    def query_entries(self, text: str, top_k: int = 5) -> list[tuple[dict[str, Any], float]]:
        """混合检索 top-k,返回 [(entry, score)]。

        向量余弦臂与 BM25 臂并行排名后 RRF 融合,专有名词/命令名靠关键词臂命中,
        paraphrasal 查询靠向量臂命中。查询解析出时间窗口时,窗口内命中按权重
        加权(×1+weight);纯时间查询(时间词之外几乎不剩内容)跳过检索臂,直接
        按窗口内时间倒序返回。两臂都无命中(模型不可用且无关键词重叠)时返回空。
        """
        top_k = max(1, top_k)
        if not self.entries:
            return []
        window = _extract_time_window(text, time.time())
        if window is not None and window[3]:
            start, end = window[0], window[1]
            in_window = [i for i, e in enumerate(self.entries) if start <= int(e.get("ts", 0)) <= end]
            in_window.sort(key=self._entry_ts, reverse=True)
            return [(self.entries[i], 0.0) for i in in_window[:top_k]]
        arms: list[list[int]] = []
        vec_arm = self._vector_ranking(text)
        if vec_arm is not None:
            arms.append(vec_arm)
        bm25_arm = self._bm25_ranking(text)
        if bm25_arm:
            arms.append(bm25_arm)
        scores = _rrf_fuse(arms)
        if window is not None:
            start, end, weight = window[0], window[1], window[2]
            for i in scores:
                if start <= int(self.entries[i].get("ts", 0)) <= end:
                    scores[i] *= 1.0 + weight
        ranked = sorted(scores.items(), key=_score_rank_key)
        return [(self.entries[i], float(s)) for i, s in ranked[:top_k]]

    def _entry_ts(self, index: int) -> int:
        return int(self.entries[index].get("ts", 0))

    def query(self, text: str, top_k: int = 5) -> list[tuple[str, float]]:
        """兼容旧接口:仅返回 [(text, score)];需要条目元数据(ts/id)时用 query_entries。"""
        return [(entry["text"], score) for entry, score in self.query_entries(text, top_k)]

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
            self._mutations += 1
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
                    self._mutations += 1
                    return True
            return False

    def list_all(self, limit: int = 20) -> list[dict[str, Any]]:
        return [dict(e) for e in self.entries[-max(1, limit) :]]

    def count(self) -> int:
        return len(self.entries)

    def is_ready(self) -> bool:
        """向量模型是否可用(False = 当前是 BM25 降级)。"""
        return self._model is not None and not self._bm25_only
