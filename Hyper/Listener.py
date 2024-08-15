from Hyper import Configurator

config = Configurator.cm.get_cfg()

if config.protocol == "OneBot":
    from Hyper.Adapters.OneBot import *
elif config.protocol == "Satori":
    from Hyper.Adapters.Satori import *
servicing = []
