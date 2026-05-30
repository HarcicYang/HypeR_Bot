from ..utils.hypetyping import Any, NoReturn, TypeVar, Callable
from ..utils.apiresponse import *
from ..events import *
from .. import events, network
from ..utils import errors

from .MilkyLib.translator import MilkyHttpConnection, msg_deid, msg_enid, to_milky_message
from .MilkyLib.Manager import Packet

import time
import threading
import asyncio
import json
import sys

config = configurator.BotConfig.get("hyper-bot")
logger = hyperogger.Logger()
logger.set_level(config.log_level)
listener_ran = False


class Actions:
    def __init__(self, cnt: MilkyHttpConnection):
        self.connection = cnt

        class CustomAction:
            def __init__(self, cnt_i: MilkyHttpConnection):
                self.connection = cnt_i

            def __getattr__(self, item) -> callable:
                async def wrapper(**kwargs) -> str:
                    packet = Packet(
                        str(item),
                        **kwargs
                    )
                    packet.send_to(self.connection)
                    return packet.echo

                return wrapper

        self.custom = CustomAction(self.connection)

    async def send(
            self, message: Union[common.Message, str], group_id: int = None, user_id: int = None
    ) -> common.Ret[MsgSendRsp]:
        if group_id is None:
            res = Packet(
                "send_private_msg",
                user_id=user_id,
                message=to_milky_message(common.Message(message))
                if not isinstance(message, common.Message) else
                to_milky_message(message),
            ).send_to(self.connection)
            ret = common.Ret(res)
            ret.data = MsgSendRsp({"message_id": msg_enid(0, res["message_seq"], user_id)})
            return ret
        else:
            res = Packet(
                "send_group_msg",
                group_id=group_id,
                message=to_milky_message(common.Message(message))
                if not isinstance(message, common.Message) else
                to_milky_message(message),
            ).send_to(self.connection)
            ret = common.Ret(res)
            ret.data = MsgSendRsp({"message_id": msg_enid(1, res["message_seq"], group_id)})
            return ret

    async def del_message(self, message_id: int) -> None:
        ...

    async def set_group_kick(self, group_id: int, user_id: int) -> None:
        ...

    async def set_group_ban(self, group_id: int, user_id: int, duration: int = 60) -> None:
        ...

    async def get_login_info(self) -> common.Ret[GetLoginInfoRsp]:
        ...

    async def get_version_info(self) -> common.Ret[GetVerInfoRsp]:
        ...

    async def send_forward_msg(self, message: common.Message) -> common.Ret[SendForwardRsp]:
        ...

    async def get_forward_msg(self, sid: str) -> common.Ret[common.Message]:
        ...

    async def forward_solve(self, message: common.Message) -> common.Message:
        ...

    async def send_group_forward_msg(self, group_id: int, message: common.Message) -> common.Ret[SendGrpForwardRsp]:
        ...

    async def set_group_add_request(self, flag: str, sub_type: str, approve: bool,
                                    reason: str = "Not Mentioned") -> None:
        ...

    async def get_stranger_info(self, user_id: int) -> common.Ret[GetStrInfoRsp]:
        ...

    async def get_group_member_info(self, group_id: int, user_id: int) -> common.Ret[GetGrpMemInfoRsp]:
        ...

    async def get_group_info(self, group_id: int) -> common.Ret[GetGrpInfoRsp]:
        ...

    async def get_status(self) -> common.Ret:
        ...

    async def set_essence_msg(self, message_id: int) -> None:
        ...

    async def set_group_special_title(self, group_id: int, user_id: int, title: str) -> None:
        ...

    async def get_msg(self, msg_id: int) -> common.Ret[GetMsgRsp]:
        ...

    async def send_callback(self, group_id: int, bot_id: int, data: dict) -> None:
        ...


async def tester(
        message_data: Union[Event, HyperNotify], actions: Actions
) -> None:
    ...


def __handler(data: Union[dict, HyperNotify], actions: Actions) -> None:
    if isinstance(data, dict):
        asyncio.run(handler(events.em.new(data), actions))
    else:
        asyncio.run(handler(data, actions))


handler: callable = tester


def reg(func: callable) -> None:
    global handler
    handler = func


connection: MilkyHttpConnection


def run() -> NoReturn:
    global connection, listener_ran
    listener_ran = True
    try:
        if handler is tester:
            raise errors.ListenerNotRegisteredError("No handler registered")
        if isinstance(config.connection, configurator.BotWSC):
            connection = network.WebsocketConnection(f"ws://{config.connection.host}:{config.connection.port}")
        elif isinstance(config.connection, configurator.BotHTTPC):
            connection = network.HTTPConnection(
                url=f"http://{config.connection.host}:{config.connection.port}",
                listener_url=f"http://{config.connection.listener_host}:{config.connection.listener_port}"
            )
        retried = 0

        while True:
            try:
                connection.connect()
            except ConnectionRefusedError or TimeoutError:
                if retried >= config.connection.retries:
                    logger.critical(f"重试次数达到最大值({config.connection.retries})，退出")
                    break

                logger.warning(f"连接建立失败，3秒后重试({retried}/{config.connection.retries})")
                retried += 1
                time.sleep(3)
                continue
            retried = 0
            logger.info(f"成功在 {connection.url} 建立连接")
            actions = Actions(connection)
            data = HyperListenerStartNotify(
                time_now=int(time.time()),
                notify_type="listener_start",
                connection=connection
            )
            threading.Thread(target=lambda: __handler(data, actions), daemon=True).start()
            while True:
                try:
                    data = connection.recv()
                except ConnectionResetError:
                    logger.error("连接断开")
                    break
                except json.decoder.JSONDecodeError:
                    logger.error("收到错误的JSON内容")
                    continue
                threading.Thread(target=lambda: __handler(data, actions), daemon=True).start()
    except KeyboardInterrupt:
        logger.warning("正在退出(Ctrl+C)")
        try:
            connection.close()
        except:
            pass
        sys.exit()


def stop() -> None:
    ...
