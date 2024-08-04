from Hyper.Configurator import *

config = cm.get_cfg()

if config.protocol == "OneBot":
    from Hyper.Adpters.OneBotLib.Manager import *