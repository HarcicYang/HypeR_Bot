import json
import threading
import time
import asyncio
import os
from typing import NoReturn

from Hyper import Network, Events, Comm
from Hyper.Utils import Errors, Logic
from Hyper.Utils.APIRsp import *
from Hyper.Comm import reports
from Hyper.Events import *

config = Configurator.cm.get_cfg()
logger = Logger.Logger()
logger.set_level(config.log_level)
listener_ran = False


class Actions:
    def __init__(self, cnt: Union[Network.WebsocketConnection, Network.HTTPConnection]):
        self.connection = cnt

        class CustomAction:
            def __init__(self, cnt_i: Union[Network.WebsocketConnection, Network.HTTPConnection]):
                self.connection = cnt_i

            def __getattr__(self, item) -> callable:
                async def wrapper(**kwargs) -> str:
                    packet = Comm.Packet(
                        str(item),
                        **kwargs
                    )
                    packet.send_to(self.connection)
                    return packet.echo

                return wrapper

        self.custom = CustomAction(self.connection)

    @Logger.AutoLogAsync.register(Logger.AutoLog.templates().send, logger)
    async def send(
            self, message: Comm.Message, group_id: int = None, user_id: int = None
    ) -> Comm.Ret[MsgSendRsp]:
        if group_id is not None:
            packet = Comm.Packet(
                "send_msg",
                group_id=group_id,
                message=await message.get()
            )
        elif user_id is not None:
            packet = Comm.Packet(
                "send_msg",
                user_id=user_id,
                message=await message.get()
            )
        else:
            raise Errors.ArgsInvalidError("'send' API requires 'group_id' or 'user_id' but none of them are provided.")
        packet.send_to(self.connection)
        return Comm.Ret.fetch(packet.echo, MsgSendRsp)

    @Logger.AutoLogAsync.register(Logger.AutoLog.templates().recall, logger)
    async def del_message(self, message_id: int) -> None:
        Comm.Packet(
            "delete_msg",
            message_id=message_id,
        ).send_to(self.connection)

    @Logger.AutoLogAsync.register(Logger.AutoLog.templates().kick, logger)
    async def set_group_kick(self, group_id: int, user_id: int) -> None:
        Comm.Packet(
            "set_group_kick",
            group_id=group_id,
            user_id=user_id,
        ).send_to(self.connection)

    @Logger.AutoLogAsync.register(Logger.AutoLog.templates().mute, logger)
    async def set_group_ban(self, group_id: int, user_id: int, duration: int = 60) -> None:
        Comm.Packet(
            "set_group_ban",
            group_id=group_id,
            user_id=user_id,
            duration=duration,
        ).send_to(self.connection)

    @Logic.Cacher().cache_async
    async def get_login_info(self) -> Comm.Ret[GetLoginInfoRsp]:
        packet = Comm.Packet("get_login_info")
        packet.send_to(self.connection)
        return Comm.Ret.fetch(packet.echo, GetLoginInfoRsp)

    @Logic.Cacher().cache_async
    async def get_version_info(self) -> Comm.Ret[GetVerInfoRsp]:
        packet = Comm.Packet("get_version_info")
        packet.send_to(self.connection)
        return Comm.Ret.fetch(packet.echo, GetVerInfoRsp)

    async def send_forward_msg(self, message: Comm.Message) -> Comm.Ret[SendForwardRsp]:
        packet = Comm.Packet(
            "send_forward_msg",
            messages=await message.get()
        )
        packet.send_to(self.connection)
        return Comm.Ret.fetch(packet.echo, SendForwardRsp)

    async def send_group_forward_msg(self, group_id: int, message: Comm.Message) -> Comm.Ret[SendGrpForwardRsp]:
        packet = Comm.Packet(
            "send_group_forward_msg",
            group_id=group_id,
            messages=await message.get()
        )
        packet.send_to(self.connection)
        return Comm.Ret.fetch(packet.echo, SendForwardRsp)

    @Logger.AutoLogAsync.register(Logger.AutoLog.templates().set_req, logger)
    async def set_group_add_request(self, flag: str, sub_type: str, approve: bool, reason: str = "Refused") -> None:
        Comm.Packet(
            "set_group_add_request",
            flag=flag,
            sub_type=sub_type,
            approve=approve,
            reason=reason
        ).send_to(self.connection)

    @Logic.Cacher().cache_async
    async def get_stranger_info(self, user_id: int) -> Comm.Ret[GetStrInfoRsp]:
        packet = Comm.Packet(
            "get_stranger_info",
            user_id=user_id,
            no_cache=True,
        )
        packet.send_to(self.connection)
        return Comm.Ret.fetch(packet.echo, GetStrInfoRsp)

    @Logic.Cacher().cache_async
    async def get_group_member_info(self, group_id: int, user_id: int) -> Comm.Ret[GetGrpMemInfoRsp]:
        packet = Comm.Packet(
            "get_group_member_info",
            group_id=group_id,
            user_id=user_id,
            no_cache=True
        )
        packet.send_to(self.connection)
        return Comm.Ret.fetch(packet.echo, GetGrpMemInfoRsp)

    @Logic.Cacher().cache_async
    async def get_group_info(self, group_id: int) -> Comm.Ret[GetGrpInfoRsp]:
        packet = Comm.Packet(
            "get_group_info",
            group_id=group_id,
            no_cache=True
        )
        packet.send_to(self.connection)
        return Comm.Ret.fetch(packet.echo, GetGrpInfoRsp)

    async def get_status(self) -> Comm.Ret:
        packet = Comm.Packet("get_status")
        packet.send_to(self.connection)
        return Comm.Ret.fetch(packet.echo)

    @Logger.AutoLogAsync.register(Logger.AutoLog.templates().set_ess, logger)
    async def set_essence_msg(self, message_id: int) -> None:
        Comm.Packet(
            "set_essence_msg",
            message_id=message_id
        ).send_to(self.connection)

    async def set_group_special_title(self, group_id: int, user_id: int, title: str) -> None:
        Comm.Packet(
            "set_group_special_title",
            group_id=group_id,
            user_id=user_id,
            special_title=title,
        ).send_to(self.connection)

    async def get_msg(self, msg_id: int) -> Comm.Ret[GetMsgRsp]:
        packet = Comm.Packet(
            "get_msg",
            message_id=msg_id
        )
        packet.send_to(self.connection)
        return Comm.Ret.fetch(packet.echo, GetMsgRsp)


async def tester(
        message_data: Union[Event, HyperNotify], actions: Actions
) -> None:
    ...


def __handler(data: Union[dict, HyperNotify], actions: Actions) -> None:
    if isinstance(data, dict):
        if data.get("echo") is not None:
            reports.put(data.get("echo"), data)
        elif data.get("post_type") == "meta_event" or data.get("user_id") == data.get("self_id"):
            pass
        else:
            asyncio.run(handler(Events.em.new(data), actions))
    else:
        asyncio.run(handler(data, actions))


handler: callable = tester


def reg(func: callable) -> None:
    global handler
    handler = func


connection: Union[Network.WebsocketConnection, Network.HTTPConnection]


def run() -> NoReturn:
    global connection, listener_ran
    listener_ran = True
    try:
        if handler is tester:
            raise Errors.ListenerNotRegisteredError("No handler registered")
        # connection = websocket.WebSocket()
        if isinstance(config.connection, Configurator.WSConnectionC):
            connection = Network.WebsocketConnection(f"ws://{config.connection.host}:{config.connection.port}")
        elif isinstance(config.connection, Configurator.HTTPConnectionC):
            connection = Network.HTTPConnection(
                url=f"http://{config.connection.host}:{config.connection.port}",
                listener_url=f"http://{config.connection.listener_host}:{config.connection.listener_port}"
            )
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
            retried = 0
            logger.log(
                f"成功在 {connection.url} 建立连接",
                level=Logger.levels.INFO
            )
            actions = Actions(connection)
            data = HyperListenerStartNotify(
                time_now=int(time.time()),
                notify_type="listener_start",
                connection=connection
            )
            threading.Thread(target=lambda: __handler(data, actions)).start()
            while True:
                try:
                    data = connection.recv()
                except ConnectionResetError:
                    logger.log("连接断开", level=Logger.levels.ERROR)
                    break
                except json.decoder.JSONDecodeError:
                    logger.log("收到错误的JSON内容", level=Logger.levels.ERROR)
                    continue
                # threading.Thread(target=lambda: asyncio.run(__handler(data, actions))).start()
                threading.Thread(target=lambda: __handler(data, actions)).start()
                # asyncio.create_task(__handler(data, actions))
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
