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
# import httpx
# import time
#
#
# start = time.time()
# httpx.get("http://127.0.0.1:8080/gen/BV1Agcoe4Ey6")
# print(time.time() - start)
#
#
# def num_format(number: int) -> str:
#     units = ['', 'k', 'M', 'B', 'T']
#     if number < 1000:
#         return str(number)
#
#     magnitude = min(len(units) - 1, int((len(str(number)) - 1) / 3))
#     number /= 1000.0 ** magnitude
#     suffix = units[magnitude]
#
#     if number == int(number):
#         return f"{int(number)}{suffix}"
#     else:
#         return f"{number:.2f}{suffix}"
#
# print(num_format(999))      # "999"
# print(num_format(1000))     # "1k"
# print(num_format(1500))     # "1.50k"
# print(num_format(1000000))  # "1M"
# print(num_format(1234567))  # "1.23M"
# print(num_format(1000000000))  # "1B"
