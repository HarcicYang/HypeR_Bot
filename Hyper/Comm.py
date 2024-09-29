from Hyper import Configurator

config = Configurator.BotConfig.get("hyper-bot")

if config.protocol == "OneBot":
    from Hyper.Adapters.OneBotLib.Manager import *
elif config.protocol == "Satori":
    from Hyper.Adapters.SatoriLib.Manager import *
elif config.protocol == "Lagrange":
    from Hyper.Adapters.LagrangeLib.Manager import *
elif config.protocol == "Kritor":
    from Hyper.Adapters.KritorLib.Manager import *

init()
