from Hyper.Comm import Message

import asyncio


async def get(self, gid: int = None, uin: int = None) -> list:
    ret = []
    for i in self.contents:
        ret.append(await i.to_elem(gid, uin))
    return ret


def get_sync(self, gid: int = None, uin: int = None) -> list:
    return asyncio.run(self.get(gid, uin))


Message.get = get
Message.get_sync = get_sync
