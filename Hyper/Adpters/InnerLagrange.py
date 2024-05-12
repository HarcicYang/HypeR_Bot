from Hyper import Manager, Logic, Configurator, Logger
from Hyper.Adpters.InnerLagrangeLib import LagrangeClient
from Hyper.Adpters.InnerLagrangeLib.Manager import Event
import asyncio
import logging
import os
import threading
from lagrange.client.client import Client
from lagrange.client.events.group import GroupMessage
from lagrange.client.events.service import ServerKick
from lagrange.info.app import app_list
from lagrange.info.device import DeviceInfo
from lagrange.info.sig import SigInfo
from lagrange.utils.sign import sign_provider

DEVICE_INFO_PATH = "./device.json"
SIGINFO_PATH = "./sig.bin"
config = Configurator.Config("config.json")
logger = Logger.Logger()
logger.set_level(config.log_level)


def get_uid(gid: int, uin: int) -> str:
    r = asyncio.run(LagrangeClient.client.get_grp_members(grp_id=gid))
    for i in r.body:
        if i.account.uin == uin:
            return i.account.uid
    return "0"


class Actions:
    def __init__(self, lagrange_client: Client):
        self.client = lagrange_client

    async def send(self, message: Manager.Message, group_id: int = None, user_id: int = None) -> None:
        message = await message.get(group_id=group_id, user_id=user_id)
        if group_id is not None:
            await self.client.send_grp_msg(msg_chain=message, grp_id=int(group_id))
            logger.log(
                f"向 {group_id} 发送消息:{str(message) if len(str(message)) < 5 else str(message)[:5] + '...'}")
        else:
            pass

    async def del_message(self, message_id: int) -> None:
        print(message_id)
        n = LagrangeClient.msg_history[message_id]
        await self.client.recall_grp_msg(grp_id=n.grp_id, seq=n.seq)

    async def set_group_kick(self, group_id: int, user_id: int) -> None:
        pass

    async def set_group_ban(self, group_id: int, user_id: int, duration: int = 60) -> None:
        pass

    @Logic.Cacher().cache
    async def get_login_info(self) -> Manager.Ret:
        pass

    @Logic.Cacher().cache
    async def get_version_info(self) -> Manager.Ret:
        return Manager.Ret({"status": "ok", "retcode": 0, "data": {"app_name": None, "app_version": None}})

    async def send_forward_msg(self, message: Manager.Message) -> Manager.Ret:
        pass

    async def send_group_forward_msg(self, group_id: int, message: Manager.Message) -> Manager.Ret:
        pass

    async def set_group_add_request(self, flag: str, sub_type: str, approve: bool, reason: str = "Refused") -> None:
        pass

    @Logic.Cacher().cache
    async def get_stranger_info(self, user_id: int) -> Manager.Ret:
        pass

    @Logic.Cacher().cache
    async def get_group_member_info(self, group_id: int, user_id: int) -> Manager.Ret:
        pass

    @Logic.Cacher().cache
    async def get_group_info(self, group_id: int) -> Manager.Ret:
        pass

    async def get_status(self) -> Manager.Ret:
        pass

    async def set_essence_msg(self, message_id: int) -> None:
        pass

    async def set_group_special_title(self, group_id: int, user_id: int, title: str) -> None:
        pass


async def __ext_handler(event: Event, actions: Actions):
    ...


ext_handler: callable = __ext_handler


def reg(func: callable):
    global ext_handler
    ext_handler = func


class InfoManager:
    def __init__(self, uin: int, device_info_path: str, sig_info_path: str):
        self.uin: int = uin
        self._device_info_path: str = device_info_path
        self._sig_info_path: str = sig_info_path
        self._device = None
        self._sig_info = None

    @property
    def device(self) -> DeviceInfo:
        assert self._device, "Device not initialized"
        return self._device

    @property
    def sig_info(self) -> SigInfo:
        assert self._sig_info, "SigInfo not initialized"
        return self._sig_info

    def save_all(self):
        with open(self._sig_info_path, "wb") as f:
            f.write(self._sig_info.dump())

        with open(self._device_info_path, "wb") as f:
            f.write(self._device.dump())

        logger.log("设备信息已保存")

    def __enter__(self):
        if os.path.isfile(self._device_info_path):
            with open(self._device_info_path, "rb") as f:
                self._device = DeviceInfo.load(f.read())
        else:
            logger.log(f"{self._device_info_path} not found, generating...")
            self._device = DeviceInfo.generate(self.uin)

        if os.path.isfile(self._sig_info_path):
            with open(self._sig_info_path, "rb") as f:
                self._sig_info = SigInfo.load(f.read())
        else:
            logger.log(f"{self._sig_info_path} not found, generating...")
            self._sig_info = SigInfo.new(8848)
        return self

    def __exit__(self, *_):
        pass


async def heartbeat_task(client: Client):
    while True:
        await client.online.wait()
        await asyncio.sleep(120)


latest_msg_id = 0


async def msg_handler(client: Client, event: GroupMessage):
    global latest_msg_id
    LagrangeClient.msg_history[latest_msg_id] = event
    latest_msg_id += 1
    event = Event(event)
    actions = Actions(client)
    await ext_handler(event, actions)


async def handle_kick(client: "Client", event: "ServerKick"):
    logger.log(f"被服务器踢出：[{event.title}] {event.tips}", level=Logger.levels.CRITICAL)
    await client.stop()


async def main_lgr():
    uin = config.others["uin"]
    sign_url = "https://sign.lagrangecore.org/api/sign"

    app = app_list["linux"]

    with InfoManager(uin, DEVICE_INFO_PATH, SIGINFO_PATH) as im:
        LagrangeClient.client = Client(
            uin,
            app,
            im.device,
            im.sig_info,
            sign_provider(sign_url) if sign_url else None,
        )
        LagrangeClient.client.events.subscribe(GroupMessage, msg_handler)
        LagrangeClient.client.events.subscribe(ServerKick, handle_kick)
        LagrangeClient.client.connect()
        logger.log("链接到腾讯QQ...")
        asyncio.create_task(heartbeat_task(LagrangeClient.client))
        if im.sig_info.d2:
            if not await LagrangeClient.client.register():
                await LagrangeClient.client.login()
        else:
            await LagrangeClient.client.login()
            logger.log("登录到腾讯QQ...")
        im.save_all()
        await LagrangeClient.client.wait_closed()


def run():
    asyncio.run(main_lgr())
