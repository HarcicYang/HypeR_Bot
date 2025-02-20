from hyperot import configurator

from cfgr.manager import Serializers

try:
    configurator.BotConfig.load_from("config.json", Serializers.JSON, "hyper-bot")
except FileNotFoundError:
    configurator.BotConfig.create_and_write("config.json", Serializers.JSON)
    print("没有找到配置文件，已自动创建，请填写后重启")
    exit(-1)

from ModuleClass import CommandHandler, command


class Tester(CommandHandler):
    @command(chain=[".test", "say"], mapping={2: "name"})
    async def test(self, name: str):
        print(name)


c = Tester(None, None)
print(c.test.if_equal([".test", "say", "harcic"]))
print(c.test.gen_args([".test", "say", "harcic"]))
