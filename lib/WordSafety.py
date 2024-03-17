import jieba
import logging

logging.getLogger("jieba").setLevel(logging.ERROR)

with open("assets/dict.txt", "r", encoding="utf-8") as f:
    words = []
    word = f.read()
    word = word.split("\n")
    for i in word:
        temp = i.split("	")
        words.append({"word": temp[0], "type": temp[1]})


class Result:
    def __init__(self, message: str, result: bool):
        self.message = message
        self.result = result


def check(text: str) -> Result:
    texts = jieba.lcut(text)
    for i in words:
        if i["word"] in texts:
            ret = Result(f"检测到类型为{i['type']}的敏感用词", False)
            return ret

    ret = Result("未检出敏感词", True)
    return ret
