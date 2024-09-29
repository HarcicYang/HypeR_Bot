from Hyper import Configurator

from cfgr.manager import Serializers

try:
    Configurator.BotConfig.load_from("config.json", Serializers.JSON, "hyper-bot")
except FileNotFoundError:
    Configurator.BotConfig.create_and_write("config.json", Serializers.JSON)
    print("没有找到配置文件，已自动创建，请填写后重启")
    exit(-1)

if True:
    import asyncio
    from typing import Union

    from Hyper import Listener, Events, Logger
    import ModuleClass
    from Hyper.Utils import Logic

ModuleClass.load()

handler_list = ModuleClass.ModuleRegister.get_registered()
config = Configurator.BotConfig.get("hyper-bot")
logger = Logger.Logger()
logger.set_level(config.log_level)


@Listener.reg
@Logic.ErrorHandler().handle_async
async def handler(event: Union[Events.Event, Events.HyperNotify], actions: Listener.Actions) -> None:
    async with ModuleClass.TaskCxt() as tasks:
        for i in handler_list:
            if i.module.filter(event, i.allowed):
                tasks.add(asyncio.create_task(i.module(actions, event).handle()))


Listener.run()
