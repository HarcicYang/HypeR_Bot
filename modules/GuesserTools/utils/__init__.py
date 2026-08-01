from typing import Any

from .languages import Library
from .languages import Word as Word

lib = Library.build("./assets/word.json")
lib_zh = lib.by_letters("zh")
lib_en = lib.by_letters("en")


class ComSet:
    def __init__(self, data: Any):
        self.data = [data]

    def __contains__(self, item: Any) -> bool:
        return item in self.data

    def append(self, data: Any) -> None:
        if data in self.data:
            self.data.append(data)
