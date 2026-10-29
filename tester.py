import logging
from collections.abc import Callable
from functools import wraps
from typing import Any

_logger = logging.getLogger(__name__)


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
        _logger.info(n**n)
        _logger.info(self.b)
        return n * n


ca = A(114514)
logging.basicConfig(level=logging.INFO, format="%(message)s")
_logger.info(ca.a(2))
