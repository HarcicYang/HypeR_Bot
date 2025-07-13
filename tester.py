from hyperot import Client, configurator
from cfgr.manager import Serializers

try:
    configurator.BotConfig.load_from("config.json", Serializers.JSON, "hyper-bot")
except FileNotFoundError:
    configurator.BotConfig.create_and_write("config.json", Serializers.JSON)
    print("没有找到配置文件，已自动创建，请填写后重启")
    exit(-1)

from hyperot import events

cli = Client()

async def test(event, actions):
    print(event)

cli.subscribe(test, events.GroupMessageEvent)
cli.run()
