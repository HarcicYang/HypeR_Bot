from ..utils.hypetyping import Any

import sys


def replace(new: Any, old: str):
    try:
        del sys.modules[old]
    except KeyError:
        pass
    finally:
        sys.modules[old] = new


def replace_listener(new: "hyperot.adapters.listener"):
    replace(new, "hyperot.adapters.listener")


def replace_common(new: "hyperot.adapters.common"):
    replace(new, "hyperot.adapters.common")


def replace_res(new: "hyperot.adapters.res"):
    replace(new, "hyperot.adapters.res")
