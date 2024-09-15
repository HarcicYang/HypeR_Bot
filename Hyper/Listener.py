from Hyper import Configurator, Events

import sys
from typing import Coroutine, Union

config = Configurator.cm.get_cfg()

if config.protocol == "OneBot":
    from Hyper.Adapters.OneBot import *
elif config.protocol == "Satori":
    from Hyper.Adapters.Satori import *
elif config.protocol == "Lagrange":
    from Hyper.Adapters.LagrangePy import *
elif config.protocol == "Kritor":
    from Hyper.Adapters.Kritor import *

