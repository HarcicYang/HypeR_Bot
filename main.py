import asyncio
from Hyper import Listener, Manager, Configurator, Logger, ModuleClass, Logic

from modules import *

handler_list = ModuleClass.ModuleRegister.get_registered()
config = Configurator.Config("config.json")
logger = Logger.Logger()
logger.set_level(config.log_level)


@Listener.reg
@Logic.ErrorHandler().handle_async
async def handler(event: Manager.Event, actions: Listener.Actions) -> None:
    tasks = []
    for i in handler_list:
        if event.post_type in i.allowed_post_types:
            tasks.append(asyncio.create_task(i.module(actions, event).handle()))
    await asyncio.gather(*tasks)


Listener.run()
