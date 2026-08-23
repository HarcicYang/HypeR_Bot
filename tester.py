from functools import wraps

def dec(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper


class A:
    def __init__(self, b: int) -> None:
        self.b = b

    @dec
    def a(self, n: int) -> int:
        print(n ** n)
        print(self.b)
        return n * n


ca = A(114514)
print(ca.a(2))



