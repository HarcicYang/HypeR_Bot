mid = "g0000000000089444674400000000000000681072"


def res(msg_id: str) -> tuple[str, int, int]:
    ret = ["", 0, 0]
    ret[0] = "group" if msg_id.startswith("g") else "private"
    msg_id = msg_id.replace("g", "").replace("p", "")
    ret[1] = int(msg_id[:20])
    ret[2] = int(msg_id[20:])
    return ret[0], ret[1], ret[2]


print(res(mid))
