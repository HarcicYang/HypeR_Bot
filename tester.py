from collections.abc import Callable
from functools import wraps
from typing import Any


def dec(func: Callable[..., Any]) -> Callable[..., Any]:
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
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


