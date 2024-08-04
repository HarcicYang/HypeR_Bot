from Hyper import Configurator

Configurator.cm = Configurator.ConfigManager(Configurator.Config(file="config.json").load_from_file())

if True:
    import asyncio
    from Hyper import Listener, Events, Logger, ModuleClass, Logic

    from modules import *

handler_list = ModuleClass.ModuleRegister.get_registered()
config = Configurator.cm.get_cfg()
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
