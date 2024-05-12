from Hyper import Configurator

config = Configurator.Config("config.json")

if config.protocol == "OneBot":
    from Hyper.Adpters.OneBot import *
elif config.protocol == "Inner":
    from Hyper.Adpters.InnerLagrange import *

servicing = []
