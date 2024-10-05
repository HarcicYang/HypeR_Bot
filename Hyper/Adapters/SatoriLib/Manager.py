from Hyper.Adapters.OneBotLib.Manager import *


class Message(Message):
    def get_sync(self) -> list:
        ret = []
        for i in self.contents:
            ret.append(i.to_proto())
        return ret
