from hyperot import configurator

from cfgr.manager import Serializers

try:
    configurator.BotConfig.load_from("config.json", Serializers.JSON, "hyper-bot")
except FileNotFoundError:
    configurator.BotConfig.create_and_write("config.json", Serializers.JSON)
    print("没有找到配置文件，已自动创建，请填写后重启")
    exit(-1)

if True:
    import asyncio
    from typing import Union

    from hyperot import listener, events, hyperogger
    import ModuleClass
    from hyperot.utils import logic

ModuleClass.load()

handler_list = ModuleClass.ModuleRegister.get_registered()
config = configurator.BotConfig.get("hyper-bot")
logger = hyperogger.Logger()
logger.set_level(config.log_level)


@listener.reg
@logic.ErrorHandler().handle_async
async def handler(event: Union[events.Event, events.HyperNotify], actions: listener.Actions) -> None:
    async with ModuleClass.TaskCxt() as tasks:
        for i in handler_list:
            if i.module.filter(event, i.allowed):
                tasks.add(asyncio.create_task(i.module(actions, event).handle()))


listener.run()
