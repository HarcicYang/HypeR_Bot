from Hyper import Configurator

config = Configurator.Config("config.json")

if config.protocol == "OneBot":
    from Hyper.Adpters.OneBotLib.Segments import *
elif config.protocol == "Inner":
    from Hyper.Adpters.InnerLagrangeLib.Segments import *
