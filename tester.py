from typing import overload, Union


@overload
def a(b: str) -> None: ...


@overload
def a(b: list) -> None: ...


def a(b: Union[str, list]) -> None:
    for i in b:
        print(i)


a("114514")
a([1, 1, 4, 5, 1, 4])