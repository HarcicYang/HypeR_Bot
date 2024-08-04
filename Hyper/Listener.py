from Hyper import Configurator

config = Configurator.cm.get_cfg()

if config.protocol == "OneBot":
    from Hyper.Adpters.OneBot import *
servicing = []
