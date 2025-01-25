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
from google import genai
from google.genai import types

key = "AIzaSyCXvzU5i27LHIheI00e-zWIDIkQ-3dgXaw"

client = genai.Client(api_key=key)
chat = client.chats.create(model="gemini-2.0-flash-exp")
response = chat.send_message(input("> "))
print(response)

