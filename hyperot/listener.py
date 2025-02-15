from . import configurator, events

config = configurator.BotConfig.get("hyper-bot")

__all__ = ["run", "stop", "Actions"]

if config.protocol == "OneBot":
    from .Adapters.OneBot import *
elif config.protocol == "Satori":
    raise NotImplementedError()
elif config.protocol == "Lagrange":
    raise NotImplementedError()
elif config.protocol == "Kritor":
    from .Adapters.Kritor import *

events.init()

# @atexit.register
# def not_running() -> None:
#     if not listener_ran:
#         print(color_txt("\n您没有运行监听器或客户端，HypeR Bot正在退出...\n", rgb(197, 37, 76)))
