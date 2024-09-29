import json
import typing
from cfgr.manager import BaseConfig

from Hyper.Utils import Logic


class BotWSC(BaseConfig):
    host: str
    port: int
    retries: int
    token: str


class BotHTTPC(BaseConfig):
    host: str
    port: int
    listener_host: str
    listener_port: int
    retries: int


class BotConfig(BaseConfig):
    protocol: str = "OneBot"
    owner: list
    black_list: list
    silents: list
    connection: dict
    connection: BotHTTPC
    connection: BotWSC
    log_level: str = "INFO"
    uin: int
    others: dict

    def custom_post(self, **kwargs):
        if self.protocol == "OneBot":
            if self.connection["mode"] == "FWS":
                self.connection = BotWSC(**self.connection)
            elif self.connection["mode"] == "HTTPC":
                self.connection = BotHTTPC(**self.connection)
