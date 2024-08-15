from Hyper.Utils.TypeExt import String
from Hyper.Events import *


class Tag:
    def __init__(self, name: str, pros: list, sub_tags: list):
        self.name = name
        self.pros = dict()
        for i in pros:
            self.pros[list(i.keys())[0]] = list(i.values())[0]
        self.sub_tags = sub_tags

    @classmethod
    def res(cls, tag: str):
        making_tag = False
        tags = []
        pros = []
        temp_tag = ""
        name = ""
        for i in range(len(tag)):
            char = tag[i]
            temp_tag += char
            if char == "<":
                tags.append(InLineText(temp_tag))
                temp_tag = "<"
                making_tag = True
            else:
                if making_tag:
                    if char == ">":
                        if tag[i - 1] == "/":
                            tags.append(SingleTag.res(temp_tag))
                            temp_tag = ""
                        else:
                            if not temp_tag.startswith("</") and not temp_tag.endswith("/>"):
                                t = String(temp_tag[1:-1]).cmdl_parse()
                                name = t.pop(0)
                                pros = t
                                finding_tag = f"</{name}>"
                                index = tag.index(finding_tag)
                                t = tag[:index + len(finding_tag)].replace(temp_tag, "").replace(finding_tag, "")
                                tags.append(Tag.res(t))
                                tag = tag.replace(t, " " * len(t))
                            temp_tag = ""
        tags.append(InLineText(temp_tag))
        new = []
        for i in tags:
            if str(i) in ["", "<"] or str(i).endswith("       <"):
                pass
            else:
                new.append(i)
        return cls(name, pros, new)


class InLineText:
    def __init__(self, content: str):
        self.text = content

    def __str__(self):
        return self.text


class SingleTag:
    def __init__(self, name: str, pros: list):
        self.name = name
        self.pros = dict()
        for i in pros:
            self.pros[list(i.keys())[0]] = list(i.values())[0]

    def __str__(self):
        pros = " ".join([f"{i}='{self.pros[i]}'" for i in self.pros])
        return f"<{self.name} {pros} />"

    @classmethod
    def res(cls, tag: str):
        t = String(tag[1:-2]).cmdl_parse()
        return cls(t.pop(0), t)


def event_res(data: dict) -> dict:
    data = data["body"]
    time = data.get("timestamp")
    self_id = Integer.convert_from(data.get("self_id"))
    user_id = Integer.convert_from(data.get("user").get("id"))
    group_id = Integer.convert_from(data.get("channel").get("id"))

