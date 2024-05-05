class ObjectedDict:
    def __init__(self, content: dict):
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

    def __str__(self) -> str:
        return self.__content.__str__()


contents = {"name": "Harcic", "content": {"age": 15, "school": "sb44"}}
new = ObjectedDict(contents)
print(new.content.age)
new.content.age = 16
print(new.content.age)
print(new)
print(type(new.raw))
