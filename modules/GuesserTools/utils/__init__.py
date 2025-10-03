from .languages import Library, Word

lib = Library.build("./assets/word.json")
lib_zh = lib.by_letters("zh")
lib_en = lib.by_letters("en")


class ComSet:
    def __init__(self, data):
        self.data = [data]

    def __contains__(self, item):
        return item in self.data

    def append(self, data):
        if data in self.data:
            self.data.append(data)
