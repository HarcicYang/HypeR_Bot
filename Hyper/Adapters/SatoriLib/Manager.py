from Hyper.Adapters.OneBotLib.Manager import *


# TODO: Rewrite in Satori format
class Packet:
    def __init__(self, endpoint: str, **kwargs):
        self.endpoint = endpoint
        self.paras = kwargs
        self.echo = f"{endpoint}_{random.randint(1000, 9999)}"

    def send_to(self, connection: Network.SatoriConnection) -> None:
        payload = self.paras
        connection.send(payload, echo=self.echo)


