# from Hyper import Configurator, Client
#
# from cfgr.manager import Serializers
#
# Configurator.BotConfig.load_from("config.json", Serializers.JSON, "hyper-bot")
# if True:
#     from Hyper import Logger
#     from Hyper.Events import GroupMessageEvent
#     from Hyper.Listener import Actions
#     from Hyper.Segments import Text, Reply
#     from Hyper.Comm import Message
#
# config = Configurator.BotConfig.get("hyper-bot")
# logger = Logger.Logger()
# logger.set_level(config.log_level)
#
#
# async def msg_handler(event: GroupMessageEvent, actions: Actions):
#     if str(event.message) == "ping":
#         await actions.send(
#             group_id=event.group_id,
#             message=Message(Reply(event.message_id), Text("pong!"))
#         )
#
#
# with Client() as cli:
#     cli.subscribe(msg_handler, GroupMessageEvent)
#     cli.run()
from Hyper.Utils.Screens import color_txt, rgb
import traceback
import sys

import asyncio


def format_exception():
    exc_type, exc_value, exc_traceback = sys.exc_info()
    formatted = color_txt("Error traceback (Recent):\n", rgb(184, 246, 255))
    tb_frames = traceback.extract_tb(exc_traceback)
    FILE = color_txt("File", rgb(85, 173, 238))
    LINE = color_txt("line", rgb(85, 173, 238))
    for frame in tb_frames:
        filename, lineno, func_name, code = frame
        formatted += f"    {FILE} \"{color_txt(filename, rgb(104, 255, 244))}\", {LINE} {lineno}, in {color_txt(func_name, rgb(70, 172, 107))}\n"
        formatted += f"        {color_txt(code, rgb(255, 255, 255))}\n"
    formatted += f"{color_txt(exc_type.__name__, rgb(255, 47, 47))}: "
    formatted += color_txt(exc_value, rgb(255, 255, 255))

    return formatted


def some_function():
    async def test():
        pass

    async def test2():
        asyncio.run(test())

    asyncio.run(test2())


try:
    some_function()
except Exception as e:
    custom_formatted_message = format_exception()
    print(custom_formatted_message)
    traceback.print_exc()
