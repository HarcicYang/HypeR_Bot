import asyncio
import traceback

import hyperot

logger = hyperot.init()

from hyperot import configurator, events, listener  # noqa: E402  # 需先 hyperot.init() 加载配置

import ModuleClass  # noqa: E402

ModuleClass.load()

handler_list = ModuleClass.ModuleRegister.get_registered()
config = configurator.BotConfig.get("hyper-bot")


@listener.reg
async def handler(event: events.Event | events.HyperNotify, actions: listener.Actions) -> None:
    try:
        # logger.debug(str(event.data))
        async with ModuleClass.TaskCxt() as tasks:
            for i in handler_list:
                if i.module.filter(event, i.allowed):
                    tasks.add(asyncio.create_task(i.module(actions, event).handle()))
    except Exception:
        logger.error(traceback.format_exc())


asyncio.run(listener.run())
