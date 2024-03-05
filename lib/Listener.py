import asyncio
import threading
import websocket
from lib import Configurator, Manager, Logger, Errors
import json
import random
import queue

reports = queue.Queue()
config = Configurator.Config("config.json")
logger = Logger.Logger()
logger.set_level(config.log_level)


def get_echo(action_name: str) -> str:
    return f"{action_name}_{random.randint(100, 999)}"


servicing = []


class Actions:
    def __init__(self, socket: websocket.WebSocket):
        self.ws = socket

    def send(self, message: Manager.Message, group_id: int = None, user_id: int = None) -> None:
        echo = get_echo("send_msg")
        if group_id is not None:
            payload = {
                "action": "send_msg",
                "params": {
                    "group_id": group_id,
                    "message": message.get(),
                },
                "echo": echo,
            }
        elif user_id is not None:
            payload = {
                "action": "send_msg",
                "params": {
                    "user_id": user_id,
                    "message": message.get(),
                },
                "echo": echo,
            }
        else:
            return None
        logger.log(f"向 {group_id} 发送消息:{str(message) if len(str(message)) < 5 else str(message)[:5] + '...'}")
        self.ws.send(json.dumps(payload))

    def del_message(self, message_id: int) -> None:
        payload = {
            "action": "delete_msg",
            "params": {
                "message_id": message_id,
            },
        }
        self.ws.send(json.dumps(payload))
        logger.log(f"撤回消息 {message_id}")

    def set_group_kick(self, group_id: int, user_id: int) -> None:
        payload = {
            "action": "set_group_kick",
            "params": {
                "group_id": group_id,
                "user_id": user_id,
            },
        }
        self.ws.send(json.dumps(payload))
        logger.log(f"将 {user_id} 移出群 {group_id}")

    def set_group_ban(self, group_id: int, user_id: int, duration: int = 60) -> None:
        payload = {
            "action": "set_group_ban",
            "params": {
                "group_id": group_id,
                "user_id": user_id,
                "duration": duration,
            },
        }
        self.ws.send(json.dumps(payload))
        logger.log(f"将 {user_id} 在 {group_id} 禁言 {duration} 秒")

    def get_login_info(self) -> Manager.Ret:
        echo = get_echo("get_login_info")
        payload = {
            "action": "get_login_info",
            "params": {},
            "echo": echo,
        }
        self.ws.send(json.dumps(payload))
        return get_ret(echo)

    def get_version_info(self) -> Manager.Ret:
        echo = get_echo("get_version_info")
        payload = {
            "action": "get_version_info",
            "params": {},
            "echo": echo,
        }
        self.ws.send(json.dumps(payload))
        return get_ret(echo)

    def send_forward_msg(self, message: Manager.Message) -> Manager.Ret:
        echo = get_echo("send_forward_msg")
        payload = {
            "action": "send_forward_msg",
            "params": {
                "message": message.get(),
            },
            "echo": echo,
        }
        self.ws.send(json.dumps(payload))
        return get_ret(echo)

    def send_group_forward_msg(self, group_id: int, message: Manager.Message) -> Manager.Ret:
        echo = get_echo("send_group_forward_msg")
        payload = {
            "action": "send_group_forward_msg",
            "params": {
                "group_id": group_id,
                "message": message.get(),
            },
        }
        self.ws.send(json.dumps(payload))
        return get_ret(echo)

    def set_group_add_request(self, flag: str, sub_type: str, approve: bool, reason: str = "Refused") -> None:
        payload = {
            "action": "set_group_add_request",
            "params": {
                "flag": flag,
                "sub_type": sub_type,
                "approve": approve,
                "reason": reason,
            },
        }
        self.ws.send(json.dumps(payload))
        logger.log(f"处理 {sub_type} 请求 {flag} 的结果为 {approve}")


def get_ret(echo: str) -> Manager.Ret:
    old = None
    while True:
        content: Manager.Ret = reports.get()
        if old is not None:
            reports.put(old)
        if content.echo == echo:
            return content
        else:
            old = content


async def tester(message_data: Manager.Event, actions: Actions) -> None:
    ...


def __handler(data: dict, actions: Actions) -> None:
    if data.get("echo") is not None:
        reports.put(Manager.Ret(data))
    elif data.get("post_type") == "meta_event" or data.get("user_id") == data.get("self_id"):
        pass
    else:
        asyncio.run(handler(Manager.Event(data), actions))


handler: callable = tester
ws: callable = tester


def reg(func: callable):
    global handler
    handler = func


def run():
    global ws
    if handler is tester:
        raise Errors.ListenerNotRegisteredError("No handler registered")
    ws = websocket.WebSocket()
    ws.connect(f"ws://{config.connection.host}:{config.connection.port}")
    logger.log("成功建立连接", level=Logger.levels.INFO)
    actions = Actions(ws)
    while True:
        try:
            data = json.loads(ws.recv())
        except KeyboardInterrupt:
            logger.log("正在退出 (Ctrl+C被按下)", level=Logger.levels.WARNING)
            ws.close()
            break
        threading.Thread(target=lambda: __handler(data, actions)).start()
