from collections.abc import Callable
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from numba import njit

    NUMBA_AVAILABLE = True
except ImportError:
    NUMBA_AVAILABLE = False

from utils import lib_zh
from utils.languages import Word, Library

my_lib = lib_zh.by_length(2)


class WordFound(Exception):
    def __init__(self, path: list[Word]):
        self.path = path


if NUMBA_AVAILABLE:
    @njit
    def _reverse_path(path):
        return path[::-1]
else:
    def _reverse_path(path):
        return path[::-1]


def trans(from_word: str, to_word: str, by: Callable[[Word], list], limit: int = 10) -> list[Word]:
    from_word = my_lib.by_equation(from_word)
    to_word = my_lib.by_equation(to_word)

    queue = deque()
    queue.append(from_word)
    visited = {from_word}
    parent = {from_word: None}
    cache = {}

    while queue:
        word = queue.popleft()
        # 回溯路径长度
        path_length = 1
        cur = word
        while parent[cur] is not None:
            cur = parent[cur]
            path_length += 1
        if path_length > limit:
            continue

        # 缓存 by(word) 结果
        if word in cache:
            next_words = cache[word]
        else:
            next_words = by(word)
            cache[word] = next_words

        for i in next_words:
            if i in visited:
                continue
            parent[i] = word
            if i == to_word:
                # 回溯路径
                path = [i]
                cur = i
                while parent[cur] is not None:
                    cur = parent[cur]
                    path.append(cur)
                path = _reverse_path(path)
                return path
            queue.append(i)
            visited.add(i)
    return []


def trans_batch(tasks, by: Callable[[Word], list], limit: int = 10, max_workers: int = 4):
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_task = {
            executor.submit(trans, from_word, to_word, by, limit): (from_word, to_word)
            for from_word, to_word in tasks
        }
        for future in as_completed(future_to_task):
            task = future_to_task[future]
            try:
                results[task] = future.result()
            except Exception as e:
                results[task] = e
    return results


if __name__ == "__main__":
    # 单任务
    for j in trans("温暖", "审批", my_lib.relatives2):  # ci bian
        print(j.word)
    # 批量并发任务示例
    # batch_tasks = [("温暖", "审批"), ("海洋", "策略")]
    # batch_results = trans_batch(batch_tasks, my_lib.relatives2)
    # for (from_word, to_word), path in batch_results.items():
    #     print(f"{from_word}->{to_word}: {[w.word for w in path]}")
