import atexit

from Hyper import Configurator, Events
from Hyper.Utils.Screens import color_txt, rgb

config = Configurator.cm.get_cfg()

if config.protocol == "OneBot":
    from Hyper.Adapters.OneBot import *
elif config.protocol == "Satori":
    from Hyper.Adapters.Satori import *
elif config.protocol == "Lagrange":
    from Hyper.Adapters.LagrangePy import *
elif config.protocol == "Kritor":
    from Hyper.Adapters.Kritor import *

Events.init()


@atexit.register
def not_running():
    if not listener_ran:
        print(color_txt("\n您没有运行监听器或客户端，HypeR Bot正在退出...\n", rgb(197, 37, 76)))
