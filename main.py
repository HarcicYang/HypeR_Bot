import asyncio
from lib import Listener, Manager, Configurator, Segements
import importlib
import gc
import modules

config = Configurator.Config("config.json")
handler_list = modules.funcs


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
    elif event.is_owner and str(event.message) == ".reload":
        try:
            load()
        except Exception as err:
            actions.send(group_id=event.group_id, message=Manager.Message(
                [Segements.Reply(event.message_id), Segements.Text("错误：" + str(err))]))
        actions.send(group_id=event.group_id, message=Manager.Message(
            [Segements.Reply(event.message_id), Segements.Text("成功")]
        ))
        return

    task_list = []
    servicing.append(event.user_id)
    for i in handler_list:
        temp_handler = i.ModuleClass(actions, event)
        task_list.append(asyncio.create_task(temp_handler.handle()))
    await asyncio.gather(*task_list)
    servicing.remove(event.user_id)

Listener.run()
