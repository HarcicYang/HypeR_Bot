import asyncio
import dataclasses
import gc
import importlib
import inspect
import json
import re
from collections.abc import Callable
from typing import Any, Generic, TypeVar, Union

from hyperot import configurator, hyperogger
from hyperot.v2 import Client, ClientAPI
from hyperot.v2.common import SceneType
from hyperot.v2.events import Event, MessageReceivedEvent
from typing_extensions import override

EventT = TypeVar("EventT", bound=Event)


class Char(str):
    @classmethod
    def convert_from(cls, obj: Union[str, "String"]):
        if len(obj) != 1:
            raise TypeError("Char is not fxxking String!")
        else:
            return cls(obj)

    @property
    def width(self) -> float:
        char = self
        if len(char) != 1:
            raise TypeError("String too long")
        o = ord(char)
        widths = [
            (126, 1),
            (159, 0),
            (687, 1),
            (710, 0),
            (711, 1),
            (727, 0),
            (733, 1),
            (879, 0),
            (1154, 1),
            (1161, 0),
            (4347, 1),
            (4447, 1.75),
            (7467, 1),
            (7521, 0),
            (8369, 1),
            (8426, 0),
            (9000, 1),
            (9002, 1.75),
            (11021, 1),
            (12350, 1.75),
            (12351, 1),
            (12438, 1.75),
            (12442, 0),
            (19893, 1.75),
            (19967, 1),
            (55203, 1.75),
            (63743, 1),
            (64106, 1.75),
            (65039, 1),
            (65059, 0),
            (65131, 1.75),
            (65279, 1),
            (65376, 1.75),
            (65500, 1),
            (65510, 1.75),
            (120831, 1),
            (262141, 1.75),
            (1114109, 1),
        ]
        if o == 0xE or o == 0xF:
            return 0
        for num, wid in widths:
            if o <= num:
                return wid
        return 1


class String(str):
    def cmdl_parse(self) -> "list[String | dict[str, str]]":
        args: list[str] = []
        temp = ""
        in_sub = False
        last_sig = ""
        for i in self if self.endswith(" ") else self + " ":
            if in_sub and i == " ":
                temp += i
            elif not in_sub and i == " ":
                args.append(temp)
                temp = ""
            elif i == '"' or i == "'":
                if not in_sub:
                    in_sub = True
                    last_sig = i
                elif i == last_sig:
                    in_sub = False
            else:
                temp += i

        res: list[String | dict[str, str]] = []

        for i in args:
            if i == "":
                continue
            if "=" in i and " " not in i:
                key, value = i.split("=", 1)
                res.append({key: value})
            elif "=" not in i:
                res.append(type(self)(i))

        return res

    def match(self, par: str) -> bool:
        return bool(re.match(par, self))

    def clear(self) -> "String":
        if len(self) != 0:
            return String("")
        else:
            return self

    def to_json(self) -> Any:
        return json.loads(self)

    def format_width(self, w_p_l: int = 110) -> "String":
        c_lis = list(map(Char.convert_from, list(self)))
        lines = []
        temp_line = ""
        temp_length = 0
        for i in c_lis:
            if i == "\n":
                lines.append(temp_line)
                temp_line = ""
                temp_length = 0
            temp_line += i
            temp_length += i.width
            if temp_length >= w_p_l:
                lines.append(temp_line)
                temp_line = ""
                temp_length = 0

        lines.append(temp_line)

        return String("\n".join(lines))


class Integer(int):
    @classmethod
    def convert_from(cls, target: Any):
        if isinstance(target, int):
            return cls(target)

        try:
            return cls(int(target))
        except Exception:
            return cls(-1)


config: configurator.BotConfig = configurator.BotConfig.get("hyper-bot")
logger = hyperogger.Logger()
logger.set_level(config.log_level)


def _as_int(value: object) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def event_user_id(event: object) -> int | None:
    return _as_int(getattr(event, "user_id", None))


def event_group_id(event: object) -> int | None:
    """v2 场景事件的群号：scene_type 为 group 时取 scene_id，否则为 None。"""
    if getattr(event, "scene_type", None) == SceneType.GROUP:
        return _as_int(getattr(event, "scene_id", None))
    return None


def is_owner(event: object) -> bool:
    uid = event_user_id(event)
    return uid is not None and uid in config.owner


def group_message(event: object) -> bool:
    """仅群消息事件，替代 v1 只注册 GroupMessageEvent 的语义。"""
    return isinstance(event, MessageReceivedEvent) and event.scene_type == SceneType.GROUP


def private_message(event: object) -> bool:
    """仅私聊消息事件，替代 v1 只注册 PrivateMessageEvent 的语义。"""
    return isinstance(event, MessageReceivedEvent) and event.scene_type == SceneType.USER


def gate(event: object) -> bool:
    """中央门控：黑名单与静言列表，语义对齐 v1 的 event.blocked / event.is_silent。"""
    uid = event_user_id(event)
    gid = event_group_id(event)
    blocked = uid in config.black_list or gid in config.black_list
    silent = uid in config.silents or gid in config.silents or 0 in config.silents
    return not (blocked or silent)


class BotContext:
    """进程级机器人上下文（当前仅 self_id，供无自带 self_id 的事件路径使用）。"""

    self_id: int = 0

    @classmethod
    def set_self_id(cls, value: int) -> None:
        cls.self_id = value


def self_id_of(event: object) -> int:
    """优先取事件自带的 self_id（OneBot 消息事件携带），否则回退 BotContext。"""
    raw = getattr(event, "self_id", None)
    as_int = _as_int(raw) if raw is not None else None
    if as_int:
        return as_int
    return BotContext.self_id


@dataclasses.dataclass
class ModuleInfo:
    is_hidden: bool = True
    module_name: str = "None"
    author: str = "None"
    version: str = "0.0"
    desc: str = "None"
    helps: str = "None"


class Module(Generic[EventT]):
    config = config

    def __init__(self, client: Client[ClientAPI], event: EventT) -> None:
        self.client: Client[ClientAPI] = client
        self.api: ClientAPI = client.api
        self.event: EventT = event

    async def handle(self) -> None:
        pass

    @staticmethod
    def info() -> ModuleInfo:
        return ModuleInfo()

    @staticmethod
    def filter(event: Any, allowed: list[Any]) -> bool:
        return any(isinstance(event, i) for i in allowed)


@dataclasses.dataclass
class CommandPara:
    name: str
    annotation: type = str
    default: annotation = ""


def para_empty(obj: Any) -> bool:
    return obj is inspect.Parameter.empty


class FieldNotEqualException(Exception):
    pass


class CommandRegistration:
    def __init__(self, chain: list[str], mapping: dict[int | str, str], function: Callable[..., Any]):
        self.chain = chain
        self.mapping = mapping
        self.function = function
        signature = inspect.signature(self.function).parameters
        self.signature: list[CommandPara] = []
        for i, j in signature.items():
            self.signature.append(
                CommandPara(
                    i,
                    j.annotation,
                    j.default,
                )
            )

    async def __call__(self, sub_self: "CommandHandler", cmds: list[Any]) -> Any:
        return await self.function(**self.gen_args(cmds, sub_self))

    @property
    def length_chain(self) -> int:
        return len(self.chain)

    def if_equal(self, cmd: list[Any]) -> bool:
        flags = [False for _ in self.chain]
        try:
            for i in range(len(self.chain)):
                if self.chain[i] == cmd[i]:
                    flags[i] = True
            if all(flags):
                return True
        except IndexError:
            return False

        return False

    def gen_args(self, cmd: list[Any], sub_self: "CommandHandler") -> dict[str, Any]:
        new: dict[str, Any] = {"self": sub_self}
        for i in self.mapping:
            if isinstance(i, int):
                try:
                    new[self.mapping[i]] = cmd[i]
                except IndexError:
                    for j in self.signature:
                        if j.name == self.mapping[i] and not para_empty(j.default):
                            new[self.mapping[i]] = j.default
                            break
                    else:
                        raise FieldNotEqualException(f"index={i}: 缺少参数")
            elif isinstance(i, str):
                have = False
                for j in cmd:
                    if isinstance(j, dict) and j.get(i):
                        have = True
                if not have:
                    for k in self.signature:
                        if k.name == self.mapping[i] and not para_empty(k.default):
                            new[self.mapping[i]] = k.default
                            continue
                    else:
                        raise FieldNotEqualException(f"缺少参数 {i}")

        return new


def command(chain: list[str], mapping: dict[int | str, str]) -> Callable[[Callable[..., Any]], CommandRegistration]:
    def decorator(func: Callable[..., Any]) -> CommandRegistration:
        return CommandRegistration(chain, mapping, func)

    return decorator


class CommandHandler(Module[MessageReceivedEvent]):
    handlers: list[CommandRegistration] = []

    @override
    async def handle(self) -> None:
        cmds = String(str(self.event.message)).cmdl_parse()
        for i in self.handlers:
            if i.if_equal(cmds):
                try:
                    await i(self, cmds)
                except Exception as e:
                    await self.api.scene(self.event.scene_type, self.event.scene_id).send(repr(e))

    def __init_subclass__(cls, **kwargs: Any) -> None:
        cls.handlers = []
        for _, attr in inspect.getmembers(cls):
            if isinstance(attr, CommandRegistration):
                cls.handlers.append(attr)


class InnerHandler:
    def __init__(self, module: type[Module[Any]], allowed: list[Any]):
        self.module = module
        self.allowed = allowed


register_modules: list[InnerHandler] = []


class ModuleRegister:
    @staticmethod
    def register(*args: Any) -> Callable[[type[Module[Any]]], type[Module[Any]]]:
        def decorator(cls: type[Module[Any]]) -> type[Module[Any]]:
            allowed = [Event] if len(args) < 1 else list(args)

            def init(self: Module[Any], client: Client[ClientAPI], event: Any) -> None:
                self.client = client
                self.api = client.api
                self.event = event

            cls.__init__ = init  # type: ignore[assignment]

            register_modules.append(InnerHandler(cls, allowed))

            return cls

        return decorator

    @staticmethod
    def get_registered() -> list[InnerHandler]:
        return register_modules


imported = None


def load() -> None:
    global imported, register_modules
    register_modules = []
    if imported is not None:
        imported.load()
        imported = importlib.reload(imported)
    else:
        imported = importlib.import_module("modules")


class TaskCxt:
    def __init__(self) -> None:
        self.tasks: list[asyncio.Task[Any]] = []

    def add(self, task: asyncio.Task[Any]) -> None:
        self.tasks.append(task)

    async def wait(self) -> None:
        await asyncio.gather(*self.tasks, return_exceptions=True)

    async def __aenter__(self) -> "TaskCxt":
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        await self.wait()
        gc.collect()
