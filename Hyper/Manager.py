from Hyper.Configurator import *

config = cm.get_cfg()

if config.protocol == "OneBot":
    from Hyper.Adapters.OneBotLib.Manager import *
elif config.protocol == "Satori":
    from Hyper.Adapters.SatoriLib.Manager import *
