import json
from dataclasses import dataclass, field
from typing import List, Callable, Dict, Literal
from collections import defaultdict

from .vec import Vector, distance


# Word对象池
class WordPool:
    _pool = {}

    @classmethod
    def get(cls, data: Dict) -> "Word":
        key = data["word"]
        if key in cls._pool:
            return cls._pool[key]
        # 支持 vector 字段
        vector_data = data.get("vector")
        vector = None
        if vector_data is not None:
            vector = Vector(*vector_data, dim=4)
        obj = Word(
            word=data["word"],
            pinyin=data["pinyin"],
            abbr=data.get("abbr"),
            length=len(data["word"]),
            explanation=data.get("explanation"),
            speech=data.get("speech", "unknown"),
            vector=vector
        )
        cls._pool[key] = obj
        return obj


@dataclass(frozen=True)
class Word:
    word: str
    pinyin: str
    abbr: str
    length: int
    explanation: str = None
    speech: str = "unknown"
    vector: Vector = field(default=None)

    @classmethod
    def build(cls, data: Dict) -> "Word":
        # 支持从 json list[int|float] 构建 vector 字段
        vector_data = data.get("vec")
        vector = None
        if vector_data is not None:
            vector = Vector(*vector_data, dim=4)
        return Word(
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
            return float('inf')
        return distance(self.vector, other.vector)


class Library:
    def __init__(self, words: List[Word]):
        self._words = words
        # 用defaultdict优化索引
        self._starts_index = defaultdict(list)
        self._ends_index = defaultdict(list)
        for w in words:
            if w.word:
                self._starts_index[w.word[0]].append(w)
                self._ends_index[w.word[-1]].append(w)

    def __repr__(self):
        return f"Library({len(self._words)}, {self._words})"

    def __add__(self, other):
        return Library(self._words + other.words)

    def __iadd__(self, other):
        self._words += other.words
        return self

    def __radd__(self, other):
        return Library(self._words + other.words)

    def __iter__(self):
        return iter(self._words)

    def __contains__(self, word):
        return word in self._words

    @classmethod
    def build(cls, file: str) -> "Library":
        with open(file, "r", encoding="utf-8") as f:
            data = json.load(f)
            pd = list(map(lambda x: Word.build(x), data))
            return cls(pd)

    @property
    def length(self) -> int:
        return len(self._words)

    @property
    def words(self) -> List[Word]:
        return self._words

    def _filter_words(self, func: Callable[[Word], bool]) -> "Library":
        return type(self)(list(filter(func, self._words)))

    def by_index(self, index: int) -> Word:
        return self._words[index]

    def by_length(self, length: int) -> "Library":
        def _filter(word: Word) -> bool:
            return word.length == length

        return self._filter_words(_filter)

    def by_letters(self, letters: Literal["zh", "en", "hy"]) -> "Library":
        def _is_zh(s: Word) -> bool:
            return all('\u4e00' <= ch <= '\u9fff' for ch in s.word) and len(s.word) > 0

        def _is_en(s: Word) -> bool:
            return all(('A' <= ch <= 'Z') or ('a' <= ch <= 'z') for ch in s.word) and len(s.word) > 0

        def _is_hy(s: Word) -> bool:
            has_chinese = False
            has_english = False
            for ch in s.word:
                if '\u4e00' <= ch <= '\u9fff':
                    has_chinese = True
                elif ('A' <= ch <= 'Z') or ('a' <= ch <= 'z'):
                    has_english = True
                else:
                    return False  # 出现了非中英文字符
            return has_chinese and has_english

        if letters == "zh":
            return self._filter_words(_is_zh)
        elif letters == "en":
            return self._filter_words(_is_en)
        elif letters == "hy":
            return self._filter_words(_is_hy)
        else:
            raise ValueError(f"Unknown letter or character type '{letters}'")

    def by_starts(self, char: str) -> "Library":
        return Library(self._starts_index[char])

    def by_ends(self, char: str) -> "Library":
        return Library(self._ends_index[char])

    def by_speech(self, speech: str) -> "Library":
        def _filter(word: Word) -> bool:
            return word.speech == speech
        return self._filter_words(_filter)

    def by_equation(self, equation: str) -> 'Word | None':
        def _filter(word: Word) -> bool:
            return equation == word.word
        filtered = self._filter_words(_filter)
        if filtered._words:
            return filtered._words[0]
        return None

    def relatives2(self, word: Word) -> list:
        # 直接返回合并后的list
        return self._starts_index[word.word[0]] + self._ends_index[word.word[1]]

    def continuous(self, word: Word) -> "Library":
        return self.by_starts(word.word[1])

    def nearest_words(self, ref_words: List[Word], speech: str, exclude: List[str], top_n: int = 10) -> List[Word]:
        pool = [w for w in self._words if w.speech == speech and w.word not in exclude and w.vector is not None]
        ref_vec_words = [w for w in ref_words if w.vector is not None]
        if not pool or not ref_vec_words:
            return []
        # 排除与参考词完全相同的词
        pool = [w for w in pool if all(w.word != ref.word for ref in ref_vec_words)]
        if not pool:
            return []
        # 计算每个库词到所有参考词的最小距离
        def min_dist(word):
            return min(word.distance_to(ref) for ref in ref_vec_words)
        pool_sorted = sorted(pool, key=min_dist)
        return pool_sorted[:min(top_n, len(pool_sorted))]

    def by_vec(self, vector: Vector, speech: str, exclude: List[str], top_n: int = 10) -> Word:
        temp_word = Word(word="", pinyin="", abbr="", length=0, vector=vector, speech=speech)
        res = self.nearest_words([temp_word], speech, exclude, top_n)
        return None if len(res) == 0 else res[0]

