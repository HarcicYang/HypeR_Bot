import logging
from jieba import lcut, set_dictionary

from Hyper import Logic

logging.getLogger("jieba").setLevel(logging.ERROR)
try:
    set_dictionary("./assets/jieba.dict.txt.small")
except OSError:
    pass


class Result:
    def __init__(self, message: str, result: bool):
        self.message = message
        self.result = result


with open("assets/dict.txt", "r", encoding="utf-8") as f:
    words: list[dict[str, str]] = []
    word = f.read()
    word = word.split("\n")
    for i in word:
        temp = i.split("	")
        words.append({"word": temp[0], "type": temp[1]})

    del i


@Logic.Cacher().cache
def check(text: str) -> Result:
    texts = lcut(text)
    for j in words:
        if j["word"] in texts:
            ret = Result(f"检测到类型为{j['type']}的敏感用词", False)
            del j
            return ret
    del j
    ret = Result("未检出敏感词", True)
    return ret
