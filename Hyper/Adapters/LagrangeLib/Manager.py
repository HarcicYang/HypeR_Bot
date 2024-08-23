from Hyper.Adapters.OneBotLib.Manager import *

import asyncio


class Message(Message):
    async def get(self, gid: int = None, uin: int = None) -> list:
        ret = []
        for i in self.contents:
            ret.append(await i.to_elem(gid, uin))
        return ret

    def get_sync(self, gid: int = None, uin: int = None) -> list:
        return asyncio.run(self.get(gid, uin))
