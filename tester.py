from typing import Union

types = [
    int,
    str,
    list,
    tuple,
    dict,
    float
]


def test(a: Union[*types]):
    print(type(a))

test(1)
