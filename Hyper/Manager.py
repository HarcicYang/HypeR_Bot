from Hyper.Configurator import *

config = Config("./config.json")

if config.protocol == "OneBot":
    from Hyper.Adpters.OneBotLib.Manager import *