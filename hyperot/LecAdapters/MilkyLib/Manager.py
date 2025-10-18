from .translator import MilkyHttpConnection


class Packet:
    def __init__(self, endpoint: str, **kwargs):
        self.endpoint = endpoint
        self.paras = kwargs

    def send_to(self, connection: MilkyHttpConnection) -> dict:
        if isinstance(connection, MilkyHttpConnection):
            return connection.http_send(self.endpoint, self.paras)
        else:
            raise ValueError(f"Invalid connection: {connection}")
