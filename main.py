import asyncio
from lib import Listener, Manager, Configurator, Logger, ModuleClass
import traceback
import importlib

importlib.import_module("modules")

handler_list = ModuleClass.ModuleRegister.get_registered()
config = Configurator.Config("config.json")
logger = Logger.Logger()
logger.set_level(config.log_level)


@Listener.reg
async def handler(event: Manager.Event, actions: Listener.Actions) -> None:
    Manager.servicing.append(event.user_id)
    try:
        tasks = [
            asyncio.create_task(i.module(actions, event).handle()) if event.post_type in i.allowed_post_types else None
            for i in handler_list]
        await asyncio.gather(*tasks)
    except:
        logger.log("出现错误：", Logger.levels.ERROR)
        traceback.print_exc()
    Manager.servicing.remove(event.user_id)


Listener.run()
