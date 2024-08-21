import json
import typing

from Hyper.Utils import Logic


class WSConnectionC:
    def __init__(self, host: str, port: int, retries: int = 0, satori_token: str = None):
        self.host: str = host
        self.port: int = port
        self.retries: int = retries
        self.token: str = satori_token

    def to_json(self) -> dict:
        return dict(
            host=self.host,
            port=self.port,
            retries=self.retries,
            satori_token=self.token
        )


class HTTPConnectionC:
    def __init__(self, host: str, port: int, listener_host: str, listener_port: int, retries: int = 0):
        self.host: str = host
        self.port: int = port
        self.listener_host: str = listener_host
        self.listener_port: int = listener_port
        self.retries: int = retries

    def to_json(self) -> dict:
        return dict(
            host=self.host,
            port=self.port,
            listener_host=self.listener_host,
            listener_port=self.listener_port,
            retries=self.retries
        )


class Config:
    def __init__(
            self,
            file: str = None,
            protocol: str = "OneBot",
            owner: list[int] = None,
            black_list: list[int] = None,
            silents: list[int] = None,
            connection: typing.Union[WSConnectionC, HTTPConnectionC] = None,
            log_level: str = "INFO",
            others: dict = None
    ):
        self.inited = False
        if file is not None:
            self.file = file
        else:
            self.protocol: str = protocol
            self.owner: list[int] = owner or list()
            self.black_list: list[int] = black_list or list()
            self.silents: list[int] = silents or list
            self.connection = connection
            self.log_level = log_level
            self.others = others or dict()
            self.inited = True

    def load_from_file(self):
        config_json = Logic.FileManager.read_as_json(self.file)

        self.protocol: str = config_json["protocol"]
        self.owner: list[int] = config_json["owner"]
        self.black_list: list[int] = config_json["black_list"]
        self.silents: list[int] = config_json["silents"]
        if config_json["Connection"]["mode"] == "FWS":
            self.connection = WSConnectionC(
                config_json["Connection"]["host"],
                config_json["Connection"]["port"],
                config_json["Connection"]["retries"],
                config_json["Connection"].get("satori_token")
            )
        elif config_json["Connection"]["mode"] == "HTTP":
            self.connection = HTTPConnectionC(
                config_json["Connection"]["host"],
                config_json["Connection"]["port"],
                config_json["Connection"]["listener_host"],
                config_json["Connection"]["listener_port"],
                config_json["Connection"]["retries"]
            )
        self.log_level = config_json["Log_level"]
        self.others = config_json["Others"]

        self.inited = True
        return self

    def dump(self, file: str = None) -> None:
        if file or self.file:
            file = file or self.file
            cfg = dict(
                owner=self.owner,
                black_list=self.black_list,
                silents=self.silents,
                Connection=self.connection.to_json(),
                log_level=self.log_level,
                protocol=self.protocol,
                Others=self.others
            )
            with open(file, "w", encoding="utf-8") as f:
                f.write(json.dumps(cfg, indent=2))


class ConfigManager:
    def __init__(self, config: Config):
        self.config: Config = config

    def get_cfg(self) -> Config:
        return self.config


cm: ConfigManager
