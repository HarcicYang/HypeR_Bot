class ObjectedDict:
    def __init__(self, content: dict = None):
        if content is None:
            self.__content = dict()
        else:
            self.__content = content

    def __getattr__(self, attr):
        if attr == "_ObjectedDict__content" or attr == "raw":
            return self.__content
        else:
            att = self.__content[attr]
        if isinstance(att, dict):
            return ObjectedDict(att)
        else:
            return att

    def __setattr__(self, attr, value):
        if attr == "_ObjectedDict__content":
            super().__setattr__(attr, value)
        else:
            self.__content[attr] = value

    def __getitem__(self, item):
        return self.__content.get(item)

    def __setitem__(self, key, value):
        if self.__content.get(key):
            self.__content[key] = value

    def __str__(self) -> str:
        return self.__content.__str__()

