from Hyper import Configurator

Configurator.init(
    Configurator.Config(
        file="config.json"
    ).load_from_file()
)

if True:
    import asyncio
    from typing import Union

    from Hyper import Listener, Events, Logger
    import ModuleClass
    from Hyper.Utils import Logic

ModuleClass.load()

handler_list = ModuleClass.ModuleRegister.get_registered()
config = Configurator.cm.get_cfg()
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
