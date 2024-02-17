import json


class Connection:
    def __init__(self, host: str, port: int):
        self.host: str = host
        self.port: int = port


class Config:
    def __init__(self, file: str):
        with open(file, "r", encoding="utf-8") as f:
            self.config_json = json.load(f)

        self.owner: list[int] = self.config_json["owner"]
        self.black_list: list[int] = self.config_json["black_list"]
        self.connection = Connection(self.config_json["Connection"]["host"], self.config_json["Connection"]["port"])
        self.log_level = self.config_json["Log_level"]
        self.others = self.config_json["Others"]
