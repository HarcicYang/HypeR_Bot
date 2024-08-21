from Hyper.Adapters.OneBot import *
from Hyper.Utils.Errors import *


class Actions(Actions):
    def __init__(self, cnt: Union[Network.WebsocketConnection, Network.HTTPConnection, Network.SatoriConnection]):
        self.connection = cnt

        class CustomAction:
            def __init__(self,
                         cnt_i: Union[Network.WebsocketConnection, Network.HTTPConnection, Network.SatoriConnection]):
                self.connection = cnt_i

            def __getattr__(self, item) -> callable:
                def wrapper(**kwargs) -> str:
                    packet = Manager.Packet(
                        str(item),
                        **kwargs
                    )
                    packet.send_to(self.connection)
                    return packet.echo

                return wrapper

        self.custom = CustomAction(self.connection)


async def __handler(data: dict, actions: Actions) -> None:
    if data["op"] == 2:
        pass
    else:
        # task = asyncio.create_task(handler(Events.em.new(data), actions))
        # timed = 0
        #
        # while not task.done():
        #     await asyncio.sleep(0.1)
        #     timed += 0.1
        #     if timed >= 30:
        #         task.cancel()
        #         logger.log(f"处理{task.get_name()}超时", level=Logger.levels.ERROR)
        #         break
        print(data)


def reg(func: callable):
    global handler
    handler = func


connection: Union[Network.WebsocketConnection, Network.SatoriConnection]


def run():
    global connection
    try:
        if handler is tester:
            raise Errors.ListenerNotRegisteredError("No handler registered")
        # connection = websocket.WebSocket()
        if isinstance(config.connection, Configurator.WSConnectionC):
            connection = Network.SatoriConnection(
                config.connection.host, config.connection.port, config.connection.token
            )
        else:
            raise ConfigError
        retried = 0
        while True:
            try:
                connection.connect()
            except ConnectionRefusedError or TimeoutError:
                if retried >= config.connection.retries:
                    logger.log(f"重试次数达到最大值({config.connection.retries})，退出", level=Logger.levels.CRITICAL)
                    break

                logger.log(f"连接建立失败，3秒后重试({retried}/{config.connection.retries})",
                           level=Logger.levels.WARNING)
                retried += 1
                time.sleep(3)
                continue
            logger.log("成功建立连接", level=Logger.levels.INFO)
            retried = 0
            actions = Actions(connection)
            while True:
                try:
                    data = connection.recv()
                except ConnectionResetError:
                    logger.log("连接断开", level=Logger.levels.ERROR)
                    break
                except json.decoder.JSONDecodeError:
                    logger.log("收到错误的JSON内容", level=Logger.levels.ERROR)
                threading.Thread(target=lambda: asyncio.run(__handler(data, actions))).start()
    except KeyboardInterrupt:
        logger.log("正在退出(Ctrl+C)", level=Logger.levels.WARNING)
        try:
            connection.close()
        except:
            pass
        os._exit(0)


def stop() -> None:
    try:
        connection.close()
    except:
        pass
    logger.log("停止运行监听器", level=Logger.levels.WARNING)
