message_types = {}


def segment_builder(sg_type: str, summary_tmp: str = None):
    # print(inspect.get_annotations(cls))
    def inner_builder(cls):
        var = dict(vars(cls))
        anns: dict = var.get("__annotations__", False) or dict()

        def init(self, *args, **kwargs):
            arg = {}
            if len(args) > 0:
                for i in args:
                    arg[list(anns.keys())[list(args).index(i)]] = i

            if len(kwargs) > 0:
                for i in kwargs:
                    try:
                        arg[i] = anns[i](kwargs[i])
                    except TypeError:
                        arg[i] = kwargs[i]
            new_arg = arg.copy()

            if len(anns) > len(arg):
                for i in anns.keys():
                    if i not in arg.keys():
                        if i not in var.keys():
                            new_arg[i] = None
                            continue
                        if not isinstance(var[i], anns[i]):
                            new_arg[i] = anns[i](var[i])
                        else:
                            new_arg[i] = var[i]

            for i in new_arg:
                setattr(self, i, new_arg[i])

        cls.__init__ = init

        def to_json(self) -> dict:
            base = {"type": sg_type, "data": {}}
            for i in anns:
                if getattr(self, i) is None:
                    continue
                if not isinstance(getattr(self, i), anns[i]):
                    base["data"][i] = anns[i](getattr(self, i))
                else:
                    base["data"][i] = getattr(self, i)
                # try:
                #     base["data"][i] = anns[i](getattr(self, i))
                # except TypeError:
                #     base["data"][i] = getattr(self, i)
            return base

        cls.to_json = to_json

        def to_str(self) -> str:
            text = summary_tmp
            if text is None:
                text = "[]"
            if "<" not in text and ">" not in text:
                return text

            for i in anns:
                if f"<{i}>" in summary_tmp:
                    try:
                        v = self.__getattribute__(i)
                    except AttributeError:
                        v = None
                    text = text.replace(f"<{i}>", str(v))

            return text

        cls.__str__ = to_str if cls().__str__() == "__not_set__" else cls.__str__

        def eq(self, other) -> bool:
            if type(self) is type(other) and self.to_json() == other.to_json():
                return True
            else:
                return False

        cls.__eq__ = eq

        def ne(self, other) -> bool:
            if type(self) is type(other) and self.to_json() == other.to_json():
                return False
            else:
                return True

        cls.__ne__ = ne

        message_types[sg_type] = {
            "type": cls,
            "args": list(anns.keys())
        }

        return cls

    return inner_builder


class Base:
    def __init__(self, *args, **kwargs): ...

    def to_json(self) -> dict: ...

    def __str__(self) -> str: return "__not_set__"

    def __eq__(self, other) -> bool: ...

    def __ne__(self, other) -> bool: ...
