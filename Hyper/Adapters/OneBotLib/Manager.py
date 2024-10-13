from Hyper import Configurator, Logger, Network
from Hyper.Utils import Logic
from Hyper.Utils.HyperTyping import OneBotJsonPacket

from typing import Union
import random
import json

# reports = queue.Queue()
reports = Logic.KeyQueue()

config: Configurator.BotConfig
logger: Logger.Logger


def init() -> None:
    global config, logger
    config = Configurator.BotConfig.get("hyper-bot")
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
            payload: OneBotJsonPacket = {
                "action": self.endpoint,
                "params": self.paras,
                "echo": self.echo,
            }
            connection.send(json.dumps(payload))

        elif isinstance(connection, Network.HTTPConnection):
            payload = self.paras
            connection.send(self.endpoint, payload, self.echo)



