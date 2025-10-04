import asyncio
import jieba.posseg as pseg
import random
import json
import os
import numpy as np
import re
from .utils import lib_zh, Library

# --- 映射预计算 ---
speech_mapping = {
    'n': 1, 'eng': 2, 'x': 3, 'm': 4, 'd': 5, 'i': 6, 's': 7, 't': 8, 'l': 9, 'nr': 10, 'nz': 11, 'c': 12,
    'r': 13, 'j': 14, 'ns': 15, 'mq': 16, 'v': 17, 'a': 18, 'q': 19, 'b': 20, 'vn': 21, 'z': 22, 'u': 23,
    'o': 24, 'nrfg': 25, 'vg': 26, 'nt': 27, 'nrt': 28, 'f': 29, 'yg': 30, 'df': 31, 'p': 32, 'g': 33,
    'ad': 34, 'zg': 35, 'ng': 36, 'mg': 37, 'an': 38, 'ag': 39, 'y': 40, 'ul': 41, 'tg': 42, 'dg': 43,
    'rg': 44, 'e': 45, 'vd': 46, 'uv': 47, 'k': 48, 'ud': 49, 'uj': 50, 'uz': 51, 'ug': 52, 'h': 53
}
for i in speech_mapping:
    speech_mapping[i] = [j.word for j in lib_zh.by_speech(i).words]

# --- 模板加载 ---
TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), '../../assets/templates.json')
with open(TEMPLATE_PATH, encoding='utf-8') as f:
    datas = json.load(f)
    TEMPLATES = datas["templates"]
    ENDINGS = datas["endings"]


# --- 异步分词 ---
async def cut_async(text: str):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: list(pseg.cut(text)))


# --- 随机词补充 ---
async def random_words_from_lib(lib: Library, speech: str, exclude: list, count: int, ref_words: list = None) -> list:
    pool = [w for w in lib.words if w.speech == speech and w.word not in exclude]
    if not pool:
        return []

    if ref_words:  # 使用参考词
        async def _nearest(w):
            nearest = await lib.nearest_words_async([w], speech, exclude, top_n=max(20, count * 2))
            return nearest[0] if nearest else w

        ref_words = await asyncio.gather(*[_nearest(x) for x in ref_words])
        candidates = await lib.nearest_words_async(ref_words, speech, exclude, top_n=max(20, count * 2))
        if candidates:
            dists = np.array([min(w.distance_to(ref) for ref in ref_words if ref.vector) for w in candidates])
            top_k = max(3, min(8, count))
            temp = 1.5
            idx_sorted = np.argsort(dists)
            top_idx = idx_sorted[:top_k]
            n_top = max(1, int(count * 0.6 + 0.5))
            result = []

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
                                rest_dists < np.percentile(rest_dists, 80))
                    mid_idx = rest_idx[mid_mask]
                    chosen_rest = np.random.choice(mid_idx if len(mid_idx) >= n_rest else rest_idx,
                                                   size=min(n_rest, len(rest_idx)), replace=False)
                    result.extend(candidates[x].word for x in chosen_rest)

            if len(result) < count:
                left = [w.word for w in pool if w.word not in result]
                if left:
                    result.extend(random.sample(left, min(count - len(result), len(left))))
            return result

    return random.sample([w.word for w in pool], min(count, len(pool)))


# --- 模板句生成 ---
def build_sentence_with_template(template, *word_lists) -> str:
    speech_keys = list(speech_mapping.keys())
    speech_map = {k: (word_lists[g] if g < len(word_lists) else []) for g, k in enumerate(speech_keys)}

    def pick(_lst, _num, _key=""):
        if not _lst:
            _lst = speech_mapping.get(_key, ["什么"])
        if _num == 1:
            chosen = random.choice(_lst)
            _lst.remove(chosen)
            return chosen
        return '、'.join(random.sample(_lst, min(_num, len(_lst))))

    s = template.get('template', '') if isinstance(template, dict) else template
    if isinstance(template, dict):
        if 'random' in template:
            s = s.replace('{|', random.choice(template['random']))
        if 'optional' in template:
            for opt in template['optional']:
                s = s.replace('{?', opt if random.random() < 0.5 else '')
        s = s.replace('{|', '').replace('{?', '')

    def repl(m):
        key = m.group(1)
        return pick(speech_map.get(key, []), 1, key)

    s = re.sub(r'\{([a-zA-Z0-9]+)}', repl, s)
    return s


# --- 主函数 ---
async def silly_chatter(user_input: str, history: list[str]) -> str:
    words_with_flags = await cut_async(user_input + "".join(history))
    words = [wf.word for wf in words_with_flags]
    if len(words) > 7:
        words = random.sample(words, 7)

    n_list, v_list, a_list, d_list, m_list, q_list, r_list, p_list, c_list, u_list, ad_list, b_list, vn_list, z_list, e_list = (
    [] for _ in range(15))
    proper_list, other_list = [], []
    punct_re = re.compile(r'^[\W_]+$', re.UNICODE)

    by_eq_cache = {w: lib_zh.by_equation(w) for w in words}
    for w, wf in zip(words, words_with_flags):
        if punct_re.match(w):
            continue
        word_obj = by_eq_cache[w]
        if word_obj:
            speech = word_obj.speech or "unknown"
            target = {
                "n": n_list, "v": v_list, "a": a_list, "d": d_list, "m": m_list, "q": q_list,
                "r": r_list, "p": p_list, "c": c_list, "u": u_list, "ad": ad_list, "b": b_list,
                "vn": vn_list, "z": z_list, "e": e_list
            }.get(speech)
            if target is not None:
                target.append(word_obj.word)
            else:
                other_list.append(word_obj.word)
        else:
            if wf.flag in ["nr", "nz", "ns", "nt", "nrt", "nrfg"]:
                proper_list.append(w)
            else:
                other_list.append(w)

    ref_words = [v for v in by_eq_cache.values() if v is not None]
    sentence_count = min(5, max(2, len(words) // 2))

    async def adder(lst, spc):
        lst += await random_words_from_lib(lib_zh, spc, lst, random.randint(1, 2), ref_words=ref_words)

    await asyncio.gather(*[adder(n_list, "n"), adder(v_list, "v"), adder(a_list, "a"),
                           adder(d_list, "d"), adder(m_list, "m"), adder(q_list, "q"),
                           adder(r_list, "r"), adder(p_list, "p"), adder(c_list, "c"),
                           adder(u_list, "u"), adder(ad_list, "ad"), adder(b_list, "b"),
                           adder(vn_list, "vn"), adder(z_list, "z"), adder(e_list, "e")])

    sentences = []
    last_template = None
    for _ in range(sentence_count):
        template = random.choice(TEMPLATES)
        while last_template and template == last_template and len(TEMPLATES) > 1:
            template = random.choice(TEMPLATES)
        last_template = template
        s = build_sentence_with_template(template, n_list, v_list, a_list, d_list, m_list, q_list,
                                         r_list, p_list, c_list, u_list, ad_list, b_list,
                                         vn_list, z_list, e_list, proper_list)
        if s.strip():
            sentences.append(s)

    if not sentences:
        sentences = [f"你说的这些词：{'、'.join(other_list)}，真有意思！"] if other_list else ["你说的我都不懂~"]

    if random.random() < 0.7:
        sentences[-1] += random.choice(ENDINGS)

    return (" ".join(sentences)).replace("}", "").replace("{", "")
