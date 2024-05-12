import json
from Hyper import Logic


class Connection:
    def __init__(self, host: str, port: int, retries: int = 0):
        self.host: str = host
        self.port: int = port
        self.retries: int = retries


class Config:
    def __init__(self, file: str):
        self.config_json = Logic.FileManager.read_as_json(file)

        self.protocol: str = self.config_json["protocol"]
        self.owner: list[int] = self.config_json["owner"]
        self.black_list: list[int] = self.config_json["black_list"]
        self.connection = Connection(
            self.config_json["Connection"]["host"],
            self.config_json["Connection"]["port"],
            self.config_json["Connection"]["retries"]
        )
        self.log_level = self.config_json["Log_level"]
        self.others = self.config_json["Others"]
