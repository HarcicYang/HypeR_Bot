import asyncio
from typing import Union
import os
import threading
import time

from Hyper.Adapters.OneBot import Actions as OneBotActions
from Hyper.Events import Event, HyperNotify, HyperListenerStartNotify
from Hyper.Network import KritorConnection
from Hyper.Utils import Errors
from Hyper import Configurator, Logger

config = Configurator.cm.get_cfg()
logger = Logger.Logger()
logger.set_level(config.log_level)


class Actions(OneBotActions):
    def __init__(self, cnt: KritorConnection):
        self.connection = cnt


async def tester(message_data: Union[Event, HyperNotify], actions: Actions) -> None:
    ...


def __handler(data: Union[dict, HyperNotify], actions: Actions) -> None:
    print(data)


handler: callable = tester


def reg(func: callable):
    global handler
    handler = func


connection: KritorConnection
listener_ran = False


def run():
    async def runner():
        global connection, listener_ran
        try:
            if handler is tester:
                raise Errors.ListenerNotRegisteredError("No handler registered")
            # connection = websocket.WebSocket()
            # if isinstance(config.connection, Configurator.WSConnectionC):
            #     connection = Network.WebsocketConnection(f"ws://{config.connection.host}:{config.connection.port}")
            # elif isinstance(config.connection, Configurator.HTTPConnectionC):
            #     connection = Network.HTTPConnection(
            #         url=f"http://{config.connection.host}:{config.connection.port}",
            #         listener_url=f"http://{config.connection.listener_host}:{config.connection.listener_port}"
            #     )
            connection = KritorConnection(
                host=config.connection.host,
                port=config.connection.port,
            )
            retried = 0
            while True:
                try:
                    connection.connect()
                except ConnectionRefusedError or TimeoutError:
                    if retried >= config.connection.retries:
                        logger.log(f"重试次数达到最大值({config.connection.retries})，退出",
                                   level=Logger.levels.CRITICAL)
                        break

                    logger.log(f"连接建立失败，3秒后重试({retried}/{config.connection.retries})",
                               level=Logger.levels.WARNING)
                    retried += 1
                    time.sleep(3)
                    continue
                logger.log("成功建立连接", level=Logger.levels.INFO)
                retried = 0
                actions = Actions(connection)
                data = HyperListenerStartNotify(
                    time_now=int(time.time()),
                    notify_type="listener_start",
                    connection=connection
                )
                threading.Thread(target=lambda: __handler(data, actions)).start()
                task = []
                while True:
                    try:
                        if not task:
                            task.append(asyncio.create_task(connection.recv()))
                        else:
                            await asyncio.sleep(1)
                    except ConnectionResetError:
                        logger.log("连接断开", level=Logger.levels.ERROR)
                        break
                    # threading.Thread(target=lambda: asyncio.run(__handler(data, actions))).start()
                    # threading.Thread(target=lambda: __handler(data, actions)).start()
                    # asyncio.create_task(__handler(data, actions))
        except KeyboardInterrupt:
            logger.log("正在退出(Ctrl+C)", level=Logger.levels.WARNING)
            try:
                connection.close()
            except:
                pass
            os._exit(0)

    asyncio.get_event_loop().run_until_complete(runner())


def stop() -> None:
    try:
        connection.close()
    except:
        pass
    logger.log("停止运行监听器", level=Logger.levels.WARNING)
