class T1:
    b = 1

    def __init__(self, a):
        self.a = a

    def __init_subclass__(cls, **kwargs):
        cls.b = kwargs.get('b')


class T2(T1, b=2):
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)


class T3(T2, b=3):
    pass


print(T3(1).b)
