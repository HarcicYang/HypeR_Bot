import asyncio
from lib import Listener, Manager, Configurator, Logger
import modules
import traceback

config = Configurator.Config("config.json")
handler_list = modules.funcs
logger = Logger.Logger()
logger.set_level(config.log_level)


@Listener.reg
async def handler(event: Manager.Event, actions: Listener.Actions) -> None:
    Manager.servicing.append(event.user_id)
    try:
        tasks = [asyncio.create_task(i.ModuleClass(actions, event).handle()) for i in handler_list]
        await asyncio.gather(*tasks)
    except:
        logger.log("出现错误：", Logger.levels.ERROR)
        traceback.print_exc()
    Manager.servicing.remove(event.user_id)


Listener.run()
