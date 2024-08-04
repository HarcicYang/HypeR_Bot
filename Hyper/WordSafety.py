import jieba
import logging
import asyncio

from Hyper import Logic

logging.getLogger("jieba").setLevel(logging.ERROR)


class Result:
    def __init__(self, message: str, result: bool):
        self.message = message
        self.result = result


class AsyncChecker:
    def __init__(self, hot_words: list[dict[str, str]]):
        self.hot_words = hot_words

    async def check(self, text: list) -> Result:
        for j in self.hot_words:
            if j["word"] in text:
                ret = Result(f"检测到类型为{j['type']}的敏感用词", False)
                return ret

        ret = Result("未检出敏感词", True)
        return ret


with open("assets/dict.txt", "r", encoding="utf-8") as f:
    words: list[dict[str, str]] = []
    word = f.read()
    word = word.split("\n")
    inner_words: list[AsyncChecker] = []
    tmp: list[dict[str, str]] = []
    for i in word:
        temp = i.split("	")
        words.append({"word": temp[0], "type": temp[1]})
        tmp.append({"word": temp[0], "type": temp[1]})
        if len(tmp) == 50:
            inner_words.append(AsyncChecker(tmp))
            tmp = []


@Logic.Cacher().cache
def check(text: str) -> Result:
    texts = jieba.lcut(text)
    for j in words:
        if j["word"] in texts:
            ret = Result(f"检测到类型为{j['type']}的敏感用词", False)
            return ret

    ret = Result("未检出敏感词", True)
    return ret


@Logic.Cacher().cache
async def check_async(text: str) -> Result:
    texts = jieba.lcut(text)
    __tasks: list[asyncio.Task] = []
    for j in inner_words:
        __tasks.append(asyncio.create_task(j.check(texts)))
    await asyncio.gather(*__tasks)
    for j in __tasks:
        if not j.result().result:
            return j.result()
    ret = Result("未检出敏感词", True)
    return ret
