import asyncio
from typing import Union

import jieba
from .utils import lib_zh, Library, Word
import random
import json
import os
import numpy as np
import jieba.posseg as pseg
import re

speech_mapping = {
    'n': 1, 'eng': 2, 'x': 3, 'm': 4, 'd': 5, 'i': 6, 's': 7, 't': 8, 'l': 9, 'nr': 10, 'nz': 11, 'c': 12,
    'r': 13, 'j': 14, 'ns': 15, 'mq': 16, 'v': 17, 'a': 18, 'q': 19, 'b': 20, 'vn': 21, 'z': 22, 'u': 23,
    'o': 24, 'nrfg': 25, 'vg': 26, 'nt': 27, 'nrt': 28, 'f': 29, 'yg': 30, 'df': 31, 'p': 32, 'g': 33,
    'ad': 34, 'zg': 35, 'ng': 36, 'mg': 37, 'an': 38, 'ag': 39, 'y': 40, 'ul': 41, 'tg': 42, 'dg': 43,
    'rg': 44, 'e': 45, 'vd': 46, 'uv': 47, 'k': 48, 'ud': 49, 'uj': 50, 'uz': 51, 'ug': 52, 'h': 53
}

for i in speech_mapping:
    speech_mapping[i] = [j.word for j in lib_zh.by_speech(i).words]

# 加载模板
TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), '../../assets/templates.json')
with open(TEMPLATE_PATH, encoding='utf-8') as f:
    datas = json.load(f)
    TEMPLATES = datas["templates"]
    # 结尾语气词
    ENDINGS = datas["endings"]


# 从库中随机补充词
async def random_words_from_lib(lib: Library, speech: str, exclude: list, count: int, ref_words: list = None) -> list:
    pool = [w for w in lib.words if w.speech == speech and w.word not in exclude]
    if not pool:
        return []
    # 灵活多样采样
    if ref_words:
        def _f(x: Word) -> Word:
            def _g(y: Union[int, float]) -> Union[int, float]:
                return ((y / (random.random() * 10)) + random.random() * 10) * np.sin(
                    (y / (random.random() * 20)) + random.random())

            for g in range(0, 4):
                x.vector.data[g] = _g(x.vector.data[g])
            _res = lib.nearest_words([x], speech, exclude, top_n=max(20, count * 2))
            return x if len(_res) == 0 else _res[0]

        ref_words = list(map(_f, ref_words))
        candidates = lib.nearest_words(ref_words, speech, exclude, top_n=max(20, count * 2))
        if candidates:
            ref_vec_words = [w for w in (ref_words if len(ref_words) > 12 else ref_words) if
                             hasattr(w, 'vector') and w.vector is not None]
            dists = np.array([min(w.distance_to(ref) for ref in ref_vec_words) for w in candidates])
            # top_k动态调整，温度参数提升多样性
            top_k = max(3, min(8, count))
            temp = 1.5
            idx_sorted = np.argsort(dists)
            top_idx = idx_sorted[:top_k]
            rest_idx = idx_sorted[top_k:]
            result = []
            # top区和剩余区采样比例动态分配
            n_top = max(1, int(count * 0.6 + 0.5))
            n_rest = count - n_top
            # top_k softmax采样（温度提升）
            if len(top_idx) > 0 and n_top > 0:
                top_dists = dists[top_idx]
                top_probs = np.exp(-top_dists / (np.std(top_dists) * temp + 1e-6))
                top_probs = top_probs / top_probs.sum()
                chosen_top = np.random.choice(top_idx, size=min(n_top, len(top_idx)), replace=False, p=top_probs)
                result += [candidates[x].word for x in chosen_top]
            # 剩余区采样：优先选距离适中（非极近、非极远）的
            if len(rest_idx) > 0 and n_rest > 0:
                rest_dists = dists[rest_idx]
                # 计算适中区间
                mid_mask = (rest_dists > np.percentile(rest_dists, 30)) & (rest_dists < np.percentile(rest_dists, 80))
                mid_idx = rest_idx[mid_mask]
                if len(mid_idx) >= n_rest:
                    chosen_rest = np.random.choice(mid_idx, size=n_rest, replace=False)
                else:
                    chosen_rest = np.random.choice(rest_idx, size=min(n_rest, len(rest_idx)), replace=False)
                result += [candidates[x].word for x in chosen_rest]
            # 若不足count则优先补充未出现过的高频词
            if len(result) < count:
                left = [w.word for w in pool if w.word not in result]
                if left:
                    result += random.sample(left, min(count - len(result), len(left)))
            return result
    # 否则随机
    return random.sample([w.word for w in pool], min(count, len(pool)))


# 用模板和词列表生成句子
def build_sentence_with_template(template, *word_lists) -> str:
    # 构建完整词性映射
    speech_keys = list(speech_mapping.keys())
    speech_map = {k: (word_lists[g] if g < len(word_lists) else []) for g, k in enumerate(speech_keys)}

    def pick(_lst, _num, _key=""):
        # 如果词表为空 → 使用兜底库
        if not _lst:
            _lst = random.choices(speech_mapping[_key], k=5) or ["什么"]
        if _num == 1:
            chosen = random.choice(_lst)
            _lst.remove(chosen)
            return chosen
        return '、'.join(random.sample(_lst, min(_num, len(_lst))))

    # 支持字典模板
    if isinstance(template, dict):
        s = template.get('template', '')
        if 'random' in template:
            rand_piece = random.choice(template['random'])
            s = s.replace('{|', rand_piece)
        if 'optional' in template:
            for opt in template['optional']:
                if random.random() < 0.5:
                    s = s.replace('{?', opt)
                else:
                    s = s.replace('{?', '')
        # 清理特殊标记
        s = s.replace('{|', '').replace('{?', '')
    else:
        s = template

        # 动态替换 {xxx}
    matches = re.findall(r'\{([a-zA-Z0-9]+)}', s)
    for key in set(matches):
        num = s.count(f'{{{key}}}')
        lst = speech_map.get(key, [])
        for _ in range(num):
            s = s.replace(f'{{{key}}}', pick(lst, 1, key), 1)

    # 清理所有遗留占位符 {xxx}
    s = re.sub(r'\{[^{}]*\}', '', s)
    s = s.replace('}', '').replace('{', '')
    return s


async def silly_chatter(user_input: str, history: list[str]) -> str:
    """
    使用模板驱动生成更丰富的傻瓜回复，混合用户输入和词库随机词。
    """
    history = list(jieba.cut("".join(history)))
    new_history = random.choices(history, k=min(len(history), 5))
    words = list(jieba.cut(user_input)) + new_history
    n_list, v_list, a_list, d_list, m_list, q_list, r_list, p_list, c_list, u_list, ad_list, b_list, vn_list, z_list, e_list = [], [], [], [], [], [], [], [], [], [], [], [], [], [], []
    proper_list = []
    other_list = []
    # 标点符号正则
    punct_re = re.compile(r'^[\W_]+$', re.UNICODE)
    # 用 jieba.posseg 标注
    for w in words:
        if punct_re.match(w):
            continue  # 排除标点
        word_obj = lib_zh.by_equation(w)
        if word_obj:
            speech = word_obj.speech if word_obj.speech else "unknown"
            if speech == "n":
                n_list.append(word_obj.word)
            elif speech == "v":
                v_list.append(word_obj.word)
            elif speech == "a":
                a_list.append(word_obj.word)
            elif speech == "d":
                d_list.append(word_obj.word)
            elif speech == "m":
                m_list.append(word_obj.word)
            elif speech == "q":
                q_list.append(word_obj.word)
            elif speech == "r":
                r_list.append(word_obj.word)
            elif speech == "p":
                p_list.append(word_obj.word)
            elif speech == "c":
                c_list.append(word_obj.word)
            elif speech == "u":
                u_list.append(word_obj.word)
            elif speech == "ad":
                ad_list.append(word_obj.word)
            elif speech == "b":
                b_list.append(word_obj.word)
            elif speech == "vn":
                vn_list.append(word_obj.word)
            elif speech == "z":
                z_list.append(word_obj.word)
            elif speech == "e":
                e_list.append(word_obj.word)
            else:
                other_list.append(word_obj.word)
        else:
            # 未识别词，判断是否专有名词
            flag = None
            for item in pseg.cut(w):
                flag = item.flag
                break
            if flag in ["nr", "nz", "ns", "nt", "nrt", "nrfg"]:
                proper_list.append(w)
            elif not punct_re.match(w):
                other_list.append(w)
    # 构建有效参考词列表，过滤掉None
    ref_words = [lib_zh.by_equation(w) for w in words if lib_zh.by_equation(w) is not None]
    sentence_count = min(5, max(2, len(words) // 2))

    async def adder(lst, spc):
        lst += await random_words_from_lib(lib_zh, spc, lst, random.randint(1, 2), ref_words=ref_words)

    tasks = []
    for k in [
        (n_list, "n"), (v_list, "v"), (a_list, "a"), (d_list, "d"), (m_list, "m"), (q_list, "q"), (r_list, "r"),
        (p_list, "p"), (c_list, "c"), (u_list, "u"), (ad_list, "ad"), (b_list, "b"), (vn_list, "vn"), (z_list, "z"),
        (e_list, "e")
    ]:
        tasks.append(adder(k[0], k[1]))
    await asyncio.gather(*tasks)

    # 生成多句回复
    sentences = []
    last_template = None

    def pick_template():
        nonlocal last_template
        new_template = random.choice(TEMPLATES)
        # 避免连续使用同一模板
        while last_template is None or (new_template == last_template and len(TEMPLATES) > 1):
            new_template = random.choice(TEMPLATES)
            if last_template is None:
                break
        last_template = new_template
        return new_template

    for _ in range(sentence_count):
        template = pick_template()
        s = build_sentence_with_template(template, n_list, v_list, a_list, d_list, m_list, q_list, r_list, p_list,
                                         c_list, u_list, ad_list, b_list, vn_list, z_list, e_list, proper_list)
        if s.strip():
            sentences.append(s)
    if not sentences:
        if other_list:
            sentences = [f"你说的这些词：{'、'.join(other_list)}，真有意思！"]
        else:
            sentences = ["你说的我都不懂~"]
    # 随机结尾
    if random.random() < 0.7:
        sentences[-1] += random.choice(ENDINGS)
    return " ".join(sentences)
