import asyncio
import json
from dataclasses import dataclass, field
from typing import List, Callable, Dict, Literal, Optional
import numpy as np

from .vec import Vector, distance


# ==============================
# Word 对象池
# ==============================
class WordPool:
    _pool: Dict[str, "Word"] = {}

    @classmethod
    def get(cls, data: Dict) -> "Word":
        """从池中获取或构造 Word"""
        key = data["word"]
        if key in cls._pool:
            return cls._pool[key]
        obj = Word.build(data)
        cls._pool[key] = obj
        return obj


# ==============================
# Word 定义
# ==============================
@dataclass(frozen=True, slots=True)
class Word:
    word: str
    pinyin: str
    abbr: Optional[str]
    length: int
    explanation: Optional[str] = None
    speech: str = "unknown"
    vector: Optional[Vector] = field(default=None)

    @classmethod
    def build(cls, data: Dict) -> "Word":
        """支持从 JSON 构建 Word"""
        vector_data = data.get("vector") or data.get("vec")
        vector = Vector(*vector_data, dim=4) if vector_data is not None else None
        return cls(
            word=data["word"],
            pinyin=data["pinyin"],
            abbr=data.get("abbr"),
            length=len(data["word"]),
            explanation=data.get("explanation"),
            speech=data.get("speech", "unknown"),
            vector=vector
        )

    def startswith(self, char: str) -> bool:
        return self.word.startswith(char)

    def endswith(self, char: str) -> bool:
        return self.word.endswith(char)

    def distance_to(self, other: "Word") -> float:
        if self.vector is None or other.vector is None:
            return float("inf")
        return distance(self.vector, other.vector)


# ==============================
# Library 词库
# ==============================
class Library:
    def __init__(self, words: List[Word]):
        self._words: List[Word] = words
        self._starts_index: Dict[str, List[Word]] = {}
        self._ends_index: Dict[str, List[Word]] = {}
        for w in words:
            if w.word:
                self._starts_index.setdefault(w.word[0], []).append(w)
                self._ends_index.setdefault(w.word[-1], []).append(w)

    def __repr__(self):
        return f"Library({len(self._words)}, ...)"

    def __add__(self, other: "Library") -> "Library":
        return Library(self._words + other.words)

    def __iadd__(self, other: "Library") -> "Library":
        self._words += other.words
        return self

    def __radd__(self, other: "Library") -> "Library":
        return Library(self._words + other.words)

    def __iter__(self):
        return iter(self._words)

    def __contains__(self, word: Word) -> bool:
        return word in self._words

    @classmethod
    def build(cls, file: str) -> "Library":
        with open(file, "r", encoding="utf-8") as f:
            data = json.load(f)
            words = [Word.build(x) for x in data]
            return cls(words)

    @property
    def length(self) -> int:
        return len(self._words)

    @property
    def words(self) -> List[Word]:
        return self._words

    def _filter_words(self, func: Callable[[Word], bool]) -> "Library":
        return type(self)([w for w in self._words if func(w)])

    def by_index(self, index: int) -> Word:
        return self._words[index]

    def by_length(self, length: int) -> "Library":
        return self._filter_words(lambda w: w.length == length)

    def by_letters(self, letters: Literal["zh", "en", "hy"]) -> "Library":
        if letters == "zh":
            return self._filter_words(
                lambda w: len(w.word) > 0 and all("\u4e00" <= ch <= "\u9fff" for ch in w.word)
            )
        elif letters == "en":
            return self._filter_words(
                lambda w: len(w.word) > 0 and all(ch.isalpha() and ch.isascii() for ch in w.word)
            )
        elif letters == "hy":
            def _is_hy(w: Word) -> bool:
                has_chinese = any("\u4e00" <= ch <= "\u9fff" for ch in w.word)
                has_english = any(ch.isalpha() and ch.isascii() for ch in w.word)
                return has_chinese and has_english
            return self._filter_words(_is_hy)
        else:
            raise ValueError(f"Unknown letter type '{letters}'")

    def by_starts(self, char: str) -> "Library":
        return Library(self._starts_index.get(char, []))

    def by_ends(self, char: str) -> "Library":
        return Library(self._ends_index.get(char, []))

    def by_speech(self, speech: str) -> "Library":
        return self._filter_words(lambda w: w.speech == speech)

    def by_equation(self, equation: str) -> Optional[Word]:
        for w in self._words:
            if w.word == equation:
                return w
        return None

    def relatives2(self, word: Word) -> List[Word]:
        return self._starts_index.get(word.word[0], []) + self._ends_index.get(word.word[-1], [])

    def continuous(self, word: Word) -> "Library":
        return self.by_starts(word.word[1]) if len(word.word) > 1 else Library([])

    def nearest_words(
        self,
        ref_words: List[Word],
        speech: str,
        exclude: List[str],
        top_n: int = 10
    ) -> List[Word]:
        pool = [w for w in self._words if w.speech == speech and w.word not in exclude and w.vector is not None]
        ref_vecs = [w.vector.data for w in ref_words if w.vector is not None]
        if not pool or not ref_vecs:
            return []

        pool_words = []
        pool_vecs = []
        for w in pool:
            if all(w.word != ref.word for ref in ref_words):
                pool_words.append(w)
                pool_vecs.append(w.vector.data)

        if not pool_words:
            return []

        pool_arr = np.vstack(pool_vecs)  # (N, d)
        ref_arr = np.vstack(ref_vecs)    # (M, d)

        # 距离矩阵 (N, M)
        dists = np.linalg.norm(pool_arr[:, None, :] - ref_arr[None, :, :], axis=-1)
        min_dists = dists.min(axis=1)

        idxs = np.argsort(min_dists)[:top_n]
        return [pool_words[i] for i in idxs]

    async def nearest_words_async(
        self,
        ref_words: List[Word],
        speech: str,
        exclude: List[str],
        top_n: int = 10
    ) -> List[Word]:
        pool = [w for w in self._words if w.speech == speech and w.word not in exclude and w.vector is not None]
        ref_vecs = [w.vector.data for w in ref_words if w.vector is not None]
        if not pool or not ref_vecs:
            return []

        pool_words = []
        pool_vecs = []

        async def _f(w: Word):
            if all(w.word != ref.word for ref in ref_words):
                pool_words.append(w)
                pool_vecs.append(w.vector.data)

        tasks = []
        for w in pool:
            tasks.append(_f(w))

        await asyncio.gather(*tasks)

        if not pool_words:
            return []

        pool_arr = np.vstack(pool_vecs)  # (N, d)
        ref_arr = np.vstack(ref_vecs)    # (M, d)

        # 距离矩阵 (N, M)
        dists = np.linalg.norm(pool_arr[:, None, :] - ref_arr[None, :, :], axis=-1)
        min_dists = dists.min(axis=1)

        idxs = np.argsort(min_dists)[:top_n]
        return [pool_words[i] for i in idxs]

    def by_vec(self, vector: Vector, speech: str, exclude: List[str], top_n: int = 10) -> Optional[Word]:
        temp_word = Word(word="", pinyin="", abbr="", length=0, vector=vector, speech=speech)
        res = self.nearest_words([temp_word], speech, exclude, top_n)
        return res[0] if res else None
