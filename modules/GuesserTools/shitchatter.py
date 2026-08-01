import asyncio
import json
import os
import random
import re
from typing import Any

import jieba.posseg as pseg
import numpy as np

from .utils import Library, Word, lib_zh

# --- 常量化 ---
PUNCT_RE = re.compile(r"^[\W_]+$", re.UNICODE)

# --- 词性词池预缓存（模块加载时一次性生成） ---
SPEECH_POOLS: dict[str, list[str]] = {}
for speech_tag in [
    "n",
    "eng",
    "x",
    "m",
    "d",
    "i",
    "s",
    "t",
    "l",
    "nr",
    "nz",
    "c",
    "r",
    "j",
    "ns",
    "mq",
    "v",
    "a",
    "q",
    "b",
    "vn",
    "z",
    "u",
    "o",
    "nrfg",
    "vg",
    "nt",
    "nrt",
    "f",
    "yg",
    "df",
    "p",
    "g",
    "ad",
    "zg",
    "ng",
    "mg",
    "an",
    "ag",
    "y",
    "ul",
    "tg",
    "dg",
    "rg",
    "e",
    "vd",
    "uv",
    "k",
    "ud",
    "uj",
    "uz",
    "ug",
    "h",
]:
    SPEECH_POOLS[speech_tag] = [w.word for w in lib_zh.by_speech(speech_tag).words]

# 保留原有 speech_mapping 结构（此时其值为全量词列表）
# 注意：此结构与 SPEECH_POOLS 实际一致，但为兼容后续代码不变，仍然保留使用
speech_mapping: dict[str, list[str]] = {tag: list(pool) for tag, pool in SPEECH_POOLS.items()}


# --- 模板加载 ---
TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "../../assets/templates.json")
with open(TEMPLATE_PATH, encoding="utf-8") as f:
    datas = json.load(f)
    TEMPLATES: list[Any] = datas["templates"]
    ENDINGS: list[str] = datas["endings"]


# --- 异步分词（不变） ---
async def cut_async(text: str):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: list(pseg.cut(text)))


# --- 优化后的随机词补充 ---
async def random_words_from_lib(
    lib: Library, speech: str, exclude: list[str], count: int, ref_words: list[Word] | None = None
) -> list[str]:
    # 从缓存池中获取该词性的全量词，排除已用词
    full_pool = SPEECH_POOLS.get(speech, [])
    pool = [w for w in full_pool if w not in exclude]
    if not pool:
        return []

    if ref_words:
        # 合并所有参考词，一次性查询最近邻候选
        candidates = await lib.nearest_words_async(ref_words, speech, exclude, top_n=max(20, count * 2))
        if candidates:
            # 计算每个候选词到参考词的最小距离
            ref_vectors = [r.vector for r in ref_words if r.vector]
            if not ref_vectors:
                return random.sample(pool, min(count, len(pool)))

            dists = np.array([min(w.distance_to(ref) for ref in ref_words if ref.vector) for w in candidates])
            # 与原版相同的采样逻辑：取前 top_k 近邻，部分按概率选，部分从中部选
            top_k = max(3, min(8, count))
            temp = 1.5
            idx_sorted = np.argsort(dists)
            top_idx = idx_sorted[:top_k]
            n_top = max(1, int(count * 0.6 + 0.5))
            result: list[str] = []

            if len(top_idx) > 0:
                top_probs = np.exp(-dists[top_idx] / (np.std(dists[top_idx]) * temp + 1e-6))
                top_probs /= top_probs.sum()
                chosen_top = np.random.choice(top_idx, size=min(n_top, len(top_idx)), replace=False, p=top_probs)
                result.extend(candidates[x].word for x in chosen_top)

            n_rest = count - len(result)
            if n_rest > 0:
                rest_idx = idx_sorted[top_k:]
                if len(rest_idx) > 0:
                    rest_dists = dists[rest_idx]
                    mid_mask = (rest_dists > np.percentile(rest_dists, 30)) & (
                        rest_dists < np.percentile(rest_dists, 80)
                    )
                    mid_idx = rest_idx[mid_mask]
                    chosen_rest = np.random.choice(
                        mid_idx if len(mid_idx) >= n_rest else rest_idx, size=min(n_rest, len(rest_idx)), replace=False
                    )
                    result.extend(candidates[x].word for x in chosen_rest)

            if len(result) < count:
                left = [w for w in pool if w not in result]
                if left:
                    result.extend(random.sample(left, min(count - len(result), len(left))))
            return result

    # 无参考词时，直接从池中随机抽样
    return random.sample(pool, min(count, len(pool)))


# --- 模板句生成（不变，仅引用外部保持原样） ---
def build_sentence_with_template(template: dict[str, Any] | str, *word_lists: list[str]) -> str:
    speech_keys = list(speech_mapping.keys())
    speech_map: dict[str, list[str]] = {
        k: (word_lists[g] if g < len(word_lists) else []) for g, k in enumerate(speech_keys)
    }

    def pick(_lst: list[str], _num: int, _key: str = "") -> str:
        if not _lst:
            _lst = speech_mapping.get(_key, ["什么"])
        if _num == 1:
            chosen = random.choice(_lst)
            _lst.remove(chosen)
            return chosen
        return "、".join(random.sample(_lst, min(_num, len(_lst))))

    s = template.get("template", "") if isinstance(template, dict) else template
    if isinstance(template, dict):
        if "random" in template:
            s = s.replace("{|", random.choice(template["random"]))
        if "optional" in template:
            for opt in template["optional"]:
                s = s.replace("{?", opt if random.random() < 0.5 else "")
        s = s.replace("{|", "").replace("{?", "")

    def repl(m: re.Match[str]) -> str:
        key = m.group(1)
        return pick(speech_map.get(key, []), 1, key)

    s = re.sub(r"\{([a-zA-Z0-9]+)}", repl, s)
    return s


# --- 主函数优化 ---
async def silly_chatter(user_input: str, history: list[str]) -> str:
    words_with_flags = await cut_async(user_input + "".join(history))
    words = [wf.word for wf in words_with_flags]
    if len(words) > 7:
        words = random.sample(words, 7)

    # 初始化词性列表（顺序与传入 build_sentence 时严格一致）
    n_list: list[str] = []
    v_list: list[str] = []
    a_list: list[str] = []
    d_list: list[str] = []
    m_list: list[str] = []
    q_list: list[str] = []
    r_list: list[str] = []
    p_list: list[str] = []
    c_list: list[str] = []
    u_list: list[str] = []
    ad_list: list[str] = []
    b_list: list[str] = []
    vn_list: list[str] = []
    z_list: list[str] = []
    e_list: list[str] = []
    proper_list: list[str] = []
    other_list: list[str] = []

    # 批量获取词对象并缓存
    by_eq_cache: dict[str, Word | None] = {}
    for w in words:
        if not PUNCT_RE.match(w):
            by_eq_cache[w] = lib_zh.by_equation(w)

    # 按词性归类（用缓存对象）
    for w in words:
        if PUNCT_RE.match(w):
            continue
        word_obj = by_eq_cache.get(w)
        if word_obj:
            speech = word_obj.speech or "unknown"
            target = {
                "n": n_list,
                "v": v_list,
                "a": a_list,
                "d": d_list,
                "m": m_list,
                "q": q_list,
                "r": r_list,
                "p": p_list,
                "c": c_list,
                "u": u_list,
                "ad": ad_list,
                "b": b_list,
                "vn": vn_list,
                "z": z_list,
                "e": e_list,
            }.get(speech)
            if target is not None:
                target.append(word_obj.word)
            else:
                other_list.append(word_obj.word)
        else:
            # 未找到词对象，按照原逻辑根据词性标记分类
            wf = next((wf for wf in words_with_flags if wf.word == w), None)
            if wf and wf.flag in ["nr", "nz", "ns", "nt", "nrt", "nrfg"]:
                proper_list.append(w)
            else:
                other_list.append(w)

    # 收集参考词对象（仅限有向量者）
    ref_words = [obj for obj in by_eq_cache.values() if obj is not None]

    sentence_count = min(5, max(2, len(words) // 2))

    # 异步补充词汇
    async def adder(lst: list[str], spc: str) -> None:
        lst += await random_words_from_lib(lib_zh, spc, lst, random.randint(1, 2), ref_words=ref_words)

    await asyncio.gather(
        *[
            adder(n_list, "n"),
            adder(v_list, "v"),
            adder(a_list, "a"),
            adder(d_list, "d"),
            adder(m_list, "m"),
            adder(q_list, "q"),
            adder(r_list, "r"),
            adder(p_list, "p"),
            adder(c_list, "c"),
            adder(u_list, "u"),
            adder(ad_list, "ad"),
            adder(b_list, "b"),
            adder(vn_list, "vn"),
            adder(z_list, "z"),
            adder(e_list, "e"),
        ]
    )

    # 生成句子
    sentences: list[str] = []
    last_template = None
    for _ in range(sentence_count):
        template = random.choice(TEMPLATES)
        while last_template and template == last_template and len(TEMPLATES) > 1:
            template = random.choice(TEMPLATES)
        last_template = template
        s = build_sentence_with_template(
            template,
            n_list,
            v_list,
            a_list,
            d_list,
            m_list,
            q_list,
            r_list,
            p_list,
            c_list,
            u_list,
            ad_list,
            b_list,
            vn_list,
            z_list,
            e_list,
            proper_list,
        )
        if s.strip():
            sentences.append(s)

    if not sentences:
        sentences = [f"你说的这些词：{'、'.join(other_list)}，真有意思！"] if other_list else ["你说的我都不懂~"]

    if random.random() < 0.7:
        sentences[-1] += random.choice(ENDINGS)

    return (" ".join(sentences)).replace("}", "").replace("{", "")
