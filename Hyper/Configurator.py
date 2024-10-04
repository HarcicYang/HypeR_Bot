from cfgr.manager import BaseConfig


class BotWSC(BaseConfig):
    mode: str = "FWS"
    host: str
    port: int
    retries: int
    token: str


class BotHTTPC(BaseConfig):
    mode: str = "HTTPC"
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
    connection: BotHTTPC
    connection: BotWSC
    connection: dict
    log_level: str = "INFO"
    uin: int
    others: dict

    def custom_post(self, **kwargs):
        if self.protocol == "OneBot":
            if self.connection["mode"] == "FWS":
                self.connection = BotWSC(**self.connection)
            elif self.connection["mode"] == "HTTPC":
                self.connection = BotHTTPC(**self.connection)
