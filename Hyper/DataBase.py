import json
import uuid


class Dataset:
    def __init__(self, path: str = "./data.json", index: str = "./index.json"):
        self.path = path
        self.index = index
        self.data = {}
        self.indexes = {}

    def load(self):
        with open(self.path, "r") as f:
            self.data = json.load(f)
        with open(self.index, "r") as f:
            self.indexes = json.load(f)

    def save(self):
        with open(self.path, "w") as f:
            json.dump(self.data, f, indent=2)
        with open(self.index, "w") as f:
            json.dump(self.indexes, f, indent=2)

    def set(self, id, key, value):
        self.data[id][key] = value
        self.save()

    def dict_set(self, id, item: dict):
        self.data[id] = item
        self.save()

    def create(self):
        id = str(uuid.uuid4())
        self.data[id] = dict()
        self.save()
        return id

    def delete(self, id: str):
        del self.data[id]
        self.save()

    def get(self, item: dict = None, id: str = None, index=True):
        if item is not None:
            itme_id = self.queue(item, index)
            if not itme_id:
                itme_id = self.create()
                self.dict_set(itme_id, item)
            return self.data[itme_id]
        elif id is not None:
            return self.data[id]
        return False

    def queue(self, key: dict, index=True):
        if index:
            try:
                return self.indexes[str(key)]
            except KeyError or TypeError:
                pass
        for k, v in key.items():
            for i in self.data:
                try:
                    if self.data[i][k] == v:
                        if index:
                            self.indexes[str(key)] = i
                        return i
                except KeyError:
                    pass
        return False

    def exist(self, item: dict = None, id: str = None, index=True):
        if item:
            return True if self.get(item, index=index) else False
        elif id:
            return True if self.get({"_id": id}, index=index) else False
        else:
            return None

    def clear(self):
        self.data = {}
        self.indexes = {}
        self.save()
