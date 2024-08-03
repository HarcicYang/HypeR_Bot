import asyncio
from Hyper import Listener, Events, Configurator, Logger, ModuleClass, Logic

from modules import *

handler_list = ModuleClass.ModuleRegister.get_registered()
config = Configurator.Config("config.json")
logger = Logger.Logger()
logger.set_level(config.log_level)


@Listener.reg
@Logic.ErrorHandler().handle_async
async def handler(event: Events.Event, actions: Listener.Actions) -> None:
    tasks = []
    for i in handler_list:
        for j in i.allowed:
            if isinstance(event, j):
                tasks.append(asyncio.create_task(i.module(actions, event).handle()))
        if event.post_type in i.allowed:
            tasks.append(asyncio.create_task(i.module(actions, event).handle()))
    await asyncio.gather(*tasks)


Listener.run()
