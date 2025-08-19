import asyncio, sys
from typing import Union
from hyperot import configurator

from cfgr.manager import Serializers  # Maybe I've forgotten sth when coding for ucfgr? IDK.

try:
    configurator.BotConfig.load_from("config.json", Serializers.JSON, "hyper-bot")
except FileNotFoundError:
    configurator.BotConfig.create_and_write("config.json", Serializers.JSON)
    print("没有找到配置文件，已自动创建，请填写后重启")
    exit(-1)
finally:
    from hyperot import adapters

    from hyperot.Adapters.OneBotLib import Res as OneBotRes

    adapters.replace_res(OneBotRes)

    from hyperot.Adapters.OneBotLib import Manager as OneBotCommon

    adapters.replace_common(OneBotCommon)

    from hyperot.Adapters import OneBot as OneBotListener

    adapters.replace_listener(OneBotListener)

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
