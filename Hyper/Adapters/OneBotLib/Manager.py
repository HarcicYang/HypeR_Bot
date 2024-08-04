from Hyper import Logic, Configurator, Logger, Network
from Hyper.Logger import levels
from Hyper.Segments import *

from typing import Union
import inspect
import random

config = Configurator.cm.get_cfg()
logger = Logger.Logger()
logger.set_level(config.log_level)

servicing = []


class Packet:
    def __init__(self, endpoint: str, **kwargs):
        self.endpoint = endpoint
        self.paras = kwargs
        self.echo = f"{endpoint}_{random.randint(1000, 9999)}"

    def send_to(self, connection: Union[Network.WebsocketConnection, Network.HTTPConnection]) -> None:
        if isinstance(connection, Network.WebsocketConnection):
            payload = {
                "action": self.endpoint,
                "params": self.paras,
                "echo": self.echo,
            }
            connection.send(json.dumps(payload))

        elif isinstance(connection, Network.HTTPConnection):
            payload = self.paras
            connection.send(self.endpoint, payload, self.echo)


class Message:
    def __init__(self, *args):
        if len(args) == 1 and isinstance(args[0], list):
            contents = args[0]
        elif len(args) >= 1:
            contents = list(args)
        else:
            contents = []
        self.contents = contents

    def add(self, content) -> None:
        self.contents.append(content)

    async def get(self) -> list:
        ret = []
        for i in self.contents:
            ret.append(i.to_json())
        return ret

    def get_sync(self) -> list:
        ret = []
        for i in self.contents:
            ret.append(i.to_json())
        return ret

    def __len__(self) -> int:
        return len(self.contents)

    def __getitem__(self, index: int):
        return self.contents[index]

    def __setitem__(self, index: int, content) -> None:
        self.contents[index] = content

    def __delitem__(self, index: int) -> None:
        del self.contents[index]

    def __iter__(self):
        for i in self.contents:
            yield i

    def __str__(self) -> str:
        return "".join([str(content) for content in self.contents])

    def __repr__(self) -> str:
        return str(self.contents)

    def __add__(self, new):
        self.contents += new.contents
        return self

    def __iadd__(self, new):
        self.contents += new.contents
        return self


class Ret:
    def __init__(self, json_data: dict):
        self.status = json_data["status"]
        self.ret_code = json_data["retcode"]
        self.data = json_data.get("data")
        self.echo = json_data.get("echo")
