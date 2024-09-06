from Hyper import Logger, Configurator
from Hyper.Utils.Logic import SimpleQueue

from lagrange import Lagrange

config = Configurator.cm.get_cfg()
logger = Logger.Logger()
logger.set_level(config.log_level)

event_queue = SimpleQueue()

lgr = Lagrange(
    config.uin,
    "linux",
    "https://sign.0w0.ing/api/sign/25765"
)
lgr.log.set_level("WARNING")


class UidCacher:
    def __init__(self):
        self.cache = {}

    def to_uid(self, uin: int) -> str:
        return self.cache.get(uin)

    def push(self, uid: str, uin: int) -> None:
        self.cache[uin] = uid


uc = UidCacher()
