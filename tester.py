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
import httpx
import time


start = time.time()
httpx.get("http://127.0.0.1/gen/BV1Agcoe4Ey6")
print(time.time() - start)

