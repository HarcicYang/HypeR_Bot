from Hyper import Configurator

import sys

config = Configurator.cm.get_cfg()

if config.protocol == "OneBot":
    from Hyper.Adapters.OneBot import *
elif config.protocol == "Satori":
    from Hyper.Adapters.Satori import *


def restart() -> None:
    stop()
    os.execv(sys.executable, ['python'] + sys.argv)
    # os._exit(1)

