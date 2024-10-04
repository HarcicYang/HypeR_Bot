from dataclasses import dataclass


@dataclass
class Word:
    include: str
    exclude: list[str]


class Checker:
    def __init__(self, words: list[Word], max_count: int = 1) -> None:
        self.words = words
        self.max_count = max_count

    def __check(self, word: str, sen: str, ignore_index: bool = False) -> bool:
        for i in word:
            if i not in sen:
                return False

        signals = [False for _ in range(len(word))]
        last_index = -1
        for i in sen:
            for j in range(len(word)):
                if i == word[j]:
                    try:
                        sen.index(i)
                    except ValueError:
                        continue
                    if j - 1 == last_index or ignore_index:
                        signals[j] = True
                        last_index = j

            tmp = list(sen)
            tmp[sen.index(i)] = " "
            sen = "".join(tmp)

        return False not in signals

    def check(self, sen: str, ignore_index: bool = False) -> bool:
        for i in self.words:
            t_sym1 = self.__check(i.include, sen, ignore_index)
            t_sym2 = True
            for j in i.exclude:
                if self.__check(j, sen, ignore_index):
                    t_sym2 = False
            if t_sym1 and not t_sym2:
                return False

            return True

        return True


checker = Checker(
    words=[
        Word(include="小溯溯", exclude=[]),
        Word(include="调教", exclude=["强调"])
    ]
)

print(checker.check("我觉得我需要好好的强调教一下小溯"))

