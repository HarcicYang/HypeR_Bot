import jieba
from .utils import lib_zh
import random
import json
import os
import numpy as np
import jieba.posseg as pseg
import re

speech_map = {
    "n": "名词",
    "v": "动词",
    "a": "形容词",
    "ad": "副形容词",
    "d": "副词",
    "m": "数词",
    "q": "量词",
    "r": "代词",
    "p": "介词",
    "c": "连词",
    "u": "助词",
    "xc": "其他词",
    "unknown": "未知词性"
}

speech_mapping = {
    'n': 1, 'eng': 2, 'x': 3, 'm': 4, 'd': 5, 'i': 6, 's': 7, 't': 8, 'l': 9, 'nr': 10, 'nz': 11, 'c': 12,
    'r': 13, 'j': 14, 'ns': 15, 'mq': 16, 'v': 17, 'a': 18, 'q': 19, 'b': 20, 'vn': 21, 'z': 22, 'u': 23,
    'o': 24, 'nrfg': 25, 'vg': 26, 'nt': 27, 'nrt': 28, 'f': 29, 'yg': 30, 'df': 31, 'p': 32, 'g': 33,
    'ad': 34, 'zg': 35, 'ng': 36, 'mg': 37, 'an': 38, 'ag': 39, 'y': 40, 'ul': 41, 'tg': 42, 'dg': 43,
    'rg': 44, 'e': 45, 'vd': 46, 'uv': 47, 'k': 48, 'ud': 49, 'uj': 50, 'uz': 51, 'ug': 52, 'h': 53
}

# 结尾语气词
endings = [" 哈哈哈~", " 你开心就好！", " 其实我也不太懂~", " 我是不是很聪明？", " 嘻嘻~"]

# 加载模板
TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "../../assets/templates.json")
with open(TEMPLATE_PATH, encoding='utf-8') as f:
    TEMPLATES = json.load(f)


# 从库中随机补充词
def random_words_from_lib(lib, speech, exclude, count, ref_words=None):
    pool = [w for w in lib.words if w.speech == speech and w.word not in exclude]
    if not pool:
        return []
    # 灵活多样采样
    if ref_words:
        candidates = lib.nearest_words(ref_words, speech, exclude, top_n=max(20, count * 2))
        if candidates:
            ref_vec_words = [w for w in ref_words if hasattr(w, 'vector') and w.vector is not None]
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
                result += [candidates[i].word for i in chosen_top]
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
                result += [candidates[i].word for i in chosen_rest]
            # 若不足count则优先补充未出现过的高频词
            if len(result) < count:
                left = [w.word for w in pool if w.word not in result]
                if left:
                    result += random.sample(left, min(count - len(result), len(left)))
            return result
    # 否则随机
    return random.sample([w.word for w in pool], min(count, len(pool)))


# 用模板和词列表生成句子
def build_sentence_with_template(template, *word_lists):
    # 构建词性到词列表的映射
    speech_keys = [
        'n', 'v', 'a', 'd', 'm', 'q', 'r', 'p', 'c', 'u', 'ad', 'b', 'vn', 'z', 'e'
    ]
    speech_map = {k: lst for k, lst in zip(speech_keys, word_lists)}

    def pick(lst, num):
        if not lst:
            return ''
        if num == 1:
            return random.choice(lst)
        return '、'.join(random.sample(lst, min(num, len(lst))))

    # 支持字符串和字典模板
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
        s = s.replace('{|', '').replace('{?', '')
    else:
        s = template
    # 动态统计所有 {xxx} 变量
    import re
    matches = re.findall(r'\{([a-zA-Z0-9]+)\}', s)
    for key in set(matches):
        num = s.count(f'{{{key}}}')
        lst = speech_map.get(key, [])
        for _ in range(num):
            s = s.replace(f'{{{key}}}', pick(lst, 1), 1)
    # 清理所有未被替换的花括号和特殊标记
    s = re.sub(r'\{[^{}]*\}', '', s)
    s = s.replace('}', '')
    return s


def silly_chatter(user_input: str) -> str:
    """
    使用模板驱动生成更丰富的傻瓜回复，混合用户输入和词库随机词。
    """
    words = list(jieba.cut(user_input))
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
    n_list += random_words_from_lib(lib_zh, "n", n_list, random.randint(1, 2), ref_words=ref_words)
    v_list += random_words_from_lib(lib_zh, "v", v_list, random.randint(1, 2), ref_words=ref_words)
    a_list += random_words_from_lib(lib_zh, "a", a_list, random.randint(1, 2), ref_words=ref_words)
    d_list += random_words_from_lib(lib_zh, "d", d_list, random.randint(0, 1), ref_words=ref_words)
    m_list += random_words_from_lib(lib_zh, "m", m_list, random.randint(0, 1), ref_words=ref_words)
    q_list += random_words_from_lib(lib_zh, "q", q_list, random.randint(0, 1), ref_words=ref_words)
    r_list += random_words_from_lib(lib_zh, "r", r_list, random.randint(0, 1), ref_words=ref_words)
    p_list += random_words_from_lib(lib_zh, "p", p_list, random.randint(0, 1), ref_words=ref_words)
    c_list += random_words_from_lib(lib_zh, "c", c_list, random.randint(0, 1), ref_words=ref_words)
    u_list += random_words_from_lib(lib_zh, "u", u_list, random.randint(0, 1), ref_words=ref_words)
    ad_list += random_words_from_lib(lib_zh, "ad", ad_list, random.randint(0, 1), ref_words=ref_words)
    b_list += random_words_from_lib(lib_zh, "b", b_list, random.randint(0, 1), ref_words=ref_words)
    vn_list += random_words_from_lib(lib_zh, "vn", vn_list, random.randint(0, 1), ref_words=ref_words)
    z_list += random_words_from_lib(lib_zh, "z", z_list, random.randint(0, 1), ref_words=ref_words)
    e_list += random_words_from_lib(lib_zh, "e", e_list, random.randint(0, 1), ref_words=ref_words)
    # 生成多句回复
    sentences = []
    for _ in range(sentence_count):
        template = random.choice(TEMPLATES)
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
        sentences[-1] += random.choice(endings)
    return " ".join(sentences)


# if __name__ == "__main__":
#     while True:
#         print(silly_chatter(input("你想说什么？ ")))
