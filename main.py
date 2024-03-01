import asyncio
from lib import Listener, Manager, Configurator, Segments, Logger
import importlib
import gc
import modules
import traceback

config = Configurator.Config("config.json")
handler_list = modules.funcs
logger = Logger.Logger()
logger.set_level(config.log_level)


def load() -> None:
    global handler_list
    gc.collect()
    importlib.reload(modules)
    handler_list = modules.funcs


servicing = []


@Listener.reg
async def handler(event: Manager.Event, actions: Listener.Actions) -> None:
    if event.user_id in servicing or event.user_id in config.black_list or event.group_id in config.black_list:
        return
    task_list = []
    servicing.append(event.user_id)
    try:
        for i in handler_list:
            temp_handler = i.ModuleClass(actions, event)
            task_list.append(asyncio.create_task(temp_handler.handle()))
        await asyncio.gather(*task_list)
    except:
        logger.log("出现错误：", Logger.levels.ERROR)
        traceback.print_exc()
    servicing.remove(event.user_id)

Listener.run()
