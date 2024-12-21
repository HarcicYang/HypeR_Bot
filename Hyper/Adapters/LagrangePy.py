from Hyper.Adapters.LagrangeLib.Res import get_msg_id, uc, get_msg_info
from Hyper.Adapters.OneBot import *
from Hyper.Adapters.LagrangeLib.LagrangeClient import lgr, event_queue
import Hyper

from lagrange.client.client import Client as LgrCli
from lagrange.client.events.service import ClientOnline


class Actions(Actions):
    def __init__(self, cli: LgrCli):
        self.client = cli

    @Logger.AutoLogAsync.register(Logger.AutoLog.templates().send, logger)
    async def send(self, message: Comm.Message, group_id: int = None, user_id: int = None) -> Comm.Ret[MsgSendRsp]:
        async def get(msg: Comm.Message, gid: int = None, uin: int = None) -> list:
            ret = []
            for i in msg.contents:
                ret.append(await i.to_elem(gid, uin))
            return ret
        chain = await get(message, group_id, user_id)
        try:
            if group_id:
                seq = await self.client.send_grp_msg(chain, group_id)
            elif user_id:
                seq = await self.client.send_friend_msg(chain, uc.to_uid(user_id))
            else:
                raise Exception()
            msg_id = get_msg_id(seq, self.client.uin, 0)
            data = {"status": "ok", "retcode": 0, "data": {"message_id": msg_id}}
        except Exception as e:
            data = {"status": "failed", "retcode": 1400, "data": None}

        return Comm.Ret(data, MsgSendRsp)

    async def get_version_info(self) -> Comm.Ret[GetVerInfoRsp]:
        return Comm.Ret(
            {
                "status": "ok",
                "retcode": 0,
                "data": {
                    "app_name": "hyper-lgr-py",
                    "app_version": Hyper.HYPER_BOT_VERSION,
                    "protocol_version": "None"
                }
            }, GetVerInfoRsp
        )

    @Logger.AutoLogAsync.register(Logger.AutoLog.templates().recall, logger)
    async def del_message(self, message_id: int) -> None:
        seq, uin, gid = get_msg_info(message_id)
        if gid != 0:
            await self.client.recall_grp_msg(gid, seq)
        else:
            pass


def __handler(data: dict, actions: Actions) -> None:
    if isinstance(data, dict):
        if data.get("echo") is not None:
            reports.put(data.get("echo"), data)
        elif data.get("post_type") == "meta_event" or data.get("user_id") == data.get("self_id"):
            pass
        else:
            asyncio.run(handler(Events.em.new(data), actions))
    else:
        asyncio.run(handler(data, actions))


def reg(func: callable):
    global handler
    handler = func


listener_ran = False


def run():
    def start_listener() -> None:
        global listener_ran
        logger.warning("lagrange-python 由于堵塞问题，日志可能存在延后")
        listener_ran = True
        try:
            if handler is tester:
                raise Errors.ListenerNotRegisteredError("No handler registered")
            while True:
                logger.log("Lagrange 已在运行", level=Logger.levels.INFO)
                actions = Actions(lgr.client)
                data = HyperListenerStartNotify(
                    time_now=int(time.time()),
                    notify_type="listener_start_lgr_py"
                )
                threading.Thread(target=lambda: __handler(data, actions), daemon=True).start()
                while True:
                    data = event_queue.get()
                    threading.Thread(target=lambda: __handler(data, actions), daemon=True).start()
        except KeyboardInterrupt:
            logger.log("正在退出(Ctrl+C)", level=Logger.levels.WARNING)
            try:
                connection.close()
            except:
                pass
            sys.exit()

    async def run_listener(_1, _2) -> None:
        threading.Thread(target=start_listener).start()

    lgr.subscribe(ClientOnline, run_listener)
    lgr.launch()


def stop() -> None:
    try:
        connection.close()
    except:
        pass
    logger.log("停止运行监听器", level=Logger.levels.WARNING)
