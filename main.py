import asyncio
import sys
import traceback

from cfgr.manager import Serializers
from hyperot import configurator
from hyperot.v2 import Client, ClientAPI
from hyperot.v2.events import ClientStartedEvent, Event
from hyperot_adapter_onebot.events import OneBotMessageReceivedEvent


def _load_config() -> configurator.BotConfig:
    try:
        configurator.BotConfig.load_from("config.json", Serializers.JSON, "hyper-bot")
    except FileNotFoundError:
        configurator.BotConfig.create_and_write("config.json", Serializers.JSON)
        print("没有找到配置文件，已自动创建，请填写后重启")
        sys.exit(-1)
    return configurator.BotConfig.get("hyper-bot")


config = _load_config()

from hyperot.protocol.builder import OneBotEventBuilder, OneBotJsonMessageBuilder  # noqa: E402, F401

import ModuleClass  # noqa: E402  # 需先加载 config.json（hyperogger 导入时读取）

ModuleClass.load()
handler_list = ModuleClass.ModuleRegister.get_registered()

client: Client[ClientAPI] = Client.from_appconfig("appconfig.json")


from modules.OneBotExtraSegments import register_extra_segments  # noqa: E402

register_extra_segments(client.adapter.segment_codec)


async def dispatch(event: Event, client: Client[ClientAPI]) -> None:
    if not ModuleClass.gate(event):
        return
    try:
        # logger.debug(str(event.data))
        async with ModuleClass.TaskCxt() as tasks:
            for i in handler_list:
                if i.module.filter(event, i.allowed):
                    tasks.add(asyncio.create_task(i.module(client, event).handle()))
    except Exception:
        ModuleClass.logger.error(traceback.format_exc())


async def on_client_started(event: ClientStartedEvent, event_client: Client[ClientAPI]) -> None:
    profile = await event_client.api.bot.profile()
    ModuleClass.BotContext.set_self_id(int(profile.user_id))


async def track_self_id(event: OneBotMessageReceivedEvent, event_client: Client[ClientAPI]) -> None:
    ModuleClass.BotContext.set_self_id(int(event.self_id))


client.subscribe(Event, dispatch)
client.subscribe(ClientStartedEvent, on_client_started)
client.subscribe(OneBotMessageReceivedEvent, track_self_id)

asyncio.run(client.run())
