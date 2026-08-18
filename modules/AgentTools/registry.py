"""Agent 工具注册/分发机制(自研,替代 HyperAG 的 match 分发链)。

- 工具 = 类方法:在 `AgentToolBase` 子类中用 `@tool()` 装饰方法,`__init_subclass__` 自动收集注册
- schema 由类型注解自动生成,工具描述取 docstring
- 三级权限:`member` / `whitelist` / `bot_owner`(层级递进)
- 分发:`ToolRegistry.dispatch(name, params, ctx)` 查表 → 权限/场景检查 → 参数注入 → 调用
- 异常照搬 HyperAG:工具内异常捕获后 `repr(e)` 作为 tool result 回填,让模型自纠
"""

import dataclasses
import inspect
import json
import os
import time
import types as _types
from collections.abc import Callable
from typing import Any, Union, cast, get_args, get_origin, get_type_hints

from hyperot import common, configurator, segments

config = configurator.BotConfig.get("hyper-bot")
CONFIG_PATH = "config.json"

# --------------------------------------------------------------------------- #
# 权限
# --------------------------------------------------------------------------- #

PERM_LEVEL: dict[str, int] = {"member": 0, "whitelist": 1, "bot_owner": 2}

# --------------------------------------------------------------------------- #
# 消息段 schema(移植自 HyperAG MESSAGE_OBJECT)
# --------------------------------------------------------------------------- #

MESSAGE_SCHEMA: dict[str, Any] = {
    "type": "array",
    "description": "标准消息类型，由消息段组合而成。支持 text / at / reply / image 四种消息段",
    "items": {
        "anyOf": [
            {
                "type": "object",
                "properties": {
                    "seg": {"type": "string", "enum": ["text"], "description": "消息段类型，必须为text"},
                    "text": {"type": "string", "description": "文本内容"},
                },
            },
            {
                "type": "object",
                "properties": {
                    "seg": {"type": "string", "enum": ["at"], "description": "消息段类型，必须为at"},
                    "qq": {"type": "string", "description": "就是user_id，与事件上报对应"},
                },
            },
            {
                "type": "object",
                "properties": {
                    "seg": {"type": "string", "enum": ["reply"], "description": "消息段类型，必须为reply"},
                    "id": {"type": "string", "description": "就是message_id，与事件上报对应"},
                },
            },
            {
                "type": "object",
                "required": ["seg", "file"],
                "properties": {
                    "seg": {"type": "string", "enum": ["image"], "description": "消息段类型，必须为image"},
                    "file": {
                        "type": "string",
                        "description": "图片文件：本地路径、http(s):// 链接或 base64: 前缀",
                    },
                    "url": {"type": "string", "description": "图片展示地址（可选）"},
                },
            },
        ]
    },
}


class SegmentsArg:
    """标记参数为「消息段数组」类型(schema 用 MESSAGE_SCHEMA)。"""


# --------------------------------------------------------------------------- #
# 注解 → schema
# --------------------------------------------------------------------------- #


def _is_optional(anno: Any) -> bool:
    origin = get_origin(anno)
    if origin in (Union, _types.UnionType):
        return type(None) in get_args(anno)
    return False


def _unwrap_optional(anno: Any) -> Any:
    origin = get_origin(anno)
    if origin in (Union, _types.UnionType):
        args = [a for a in get_args(anno) if a is not type(None)]
        return args[0] if len(args) == 1 else anno
    return anno


def annotation_to_schema(anno: Any) -> dict[str, Any]:
    if anno is SegmentsArg:
        return MESSAGE_SCHEMA
    if anno is int:
        return {"type": "integer"}
    if anno is str:
        return {"type": "string"}
    if anno is float:
        return {"type": "number"}
    if anno is bool:
        return {"type": "boolean"}
    origin = get_origin(anno)
    if anno is list or origin is list:
        return {"type": "array"}
    if anno is dict or origin is dict:
        return {"type": "object"}
    return {"type": "object"}


# --------------------------------------------------------------------------- #
# 注册与分发
# --------------------------------------------------------------------------- #


class ToolParamError(Exception):
    pass


@dataclasses.dataclass
class ToolRegistration:
    name: str
    instance: Any  # 工具类实例(用于绑定方法)
    method: Callable[..., Any]  # 绑定方法
    perm: str
    scenes: tuple[str, ...]
    desc: str
    schema: dict[str, Any]
    required: list[str]
    hints: dict[str, Any]  # 参数类型注解(用于参数注入时的类型强制转换)
    release: bool = False  # 调用后释放本轮:主 Agent 不再请求后续 Completion(用于投喂 SubAgent 等长程任务)
    group: str = "general"  # 工具分组(声明用途分类,如 qq/info/code/github/memory/subagent)
    main_visible: bool = True  # 主 Agent 可见
    sub_visible: bool = True  # SubAgent 可见

    def visible_for(self, role: str) -> bool:
        if role == "sub":
            return self.sub_visible
        return self.main_visible

    def serialize_openai(self) -> dict[str, Any]:
        params = dict(self.schema)
        if self.required:
            params["required"] = list(self.required)
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.desc,
                "parameters": params,
            },
        }

    def inject_params(self, params: dict[str, Any]) -> dict[str, Any]:
        """按签名注入参数;模型可能给出字符串形式的数字,按注解强制转换。"""
        sig = inspect.signature(self.method)
        kwargs: dict[str, Any] = {}
        for pname, p in sig.parameters.items():
            if pname in ("self", "ctx"):
                continue
            if pname in params:
                kwargs[pname] = _coerce(self.hints.get(pname, Any), params[pname])
            elif p.default is not inspect.Parameter.empty:
                kwargs[pname] = p.default
            else:
                raise ToolParamError(f"缺少参数 {pname}")
        return kwargs


def _coerce(anno: Any, value: Any) -> Any:
    """把模型给的参数值强制转换为注解声明的类型(带注解参数已保证 required/类型)。"""
    anno = _unwrap_optional(anno)
    if anno is int and not isinstance(value, int):
        return int(value)
    if anno is str and not isinstance(value, str):
        return str(value)
    if anno is float and not isinstance(value, float):
        return float(value)
    return value


class ToolRegistry:
    _tools: dict[str, ToolRegistration] = {}
    _disabled: dict[str, float] = {}
    PERMANENT = -1.0

    # -- 动态禁用/启用状态(持久化到 config.json 的 others.agent_func_disabled) --

    @classmethod
    def _prune_expired(cls) -> None:
        """清掉已到期的禁用条目(惰性;不写盘)。"""
        now = time.time()
        expired = [n for n, until in cls._disabled.items() if until != cls.PERMANENT and until <= now]
        for n in expired:
            cls._disabled.pop(n, None)

    @classmethod
    def _load_disabled(cls) -> None:
        """启动时从 config.others 读回禁用状态;非法条目忽略。"""
        cls._disabled = {}
        raw = config.others.get("agent_func_disabled") or {}
        if isinstance(raw, dict):
            for name, value in raw.items():
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    cls._disabled[str(name)] = float(value)

    @classmethod
    def _save_disabled(cls) -> None:
        """持久化到 config.json,并同步内存 config.others。"""
        cls._prune_expired()
        with open(CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
        others = cfg.setdefault("others", {})
        others["agent_func_disabled"] = {name: until for name, until in cls._disabled.items()}
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)
        config.others["agent_func_disabled"] = others["agent_func_disabled"]

    @classmethod
    def is_disabled(cls, name: str) -> bool:
        cls._prune_expired()
        return name in cls._disabled

    @classmethod
    def disabled_until(cls, name: str) -> float | None:
        """返回 None=未禁用;PERMANENT(-1)=永久;其他=到期时间戳(epoch 秒)。"""
        cls._prune_expired()
        return cls._disabled.get(name)

    @classmethod
    def registrations(cls) -> list[ToolRegistration]:
        """按分组/名称排序返回全部工具注册信息(含禁用中的)。"""
        return sorted(cls._tools.values(), key=lambda t: (t.group, t.name))

    @classmethod
    def disable_tool(cls, name: str, minutes: float | None, duration_text: str = "") -> str:
        """禁用工具。minutes=None 表示永久禁用,直到手动启用。返回中文结果。"""
        if cls._tools.get(name) is None:
            return f"工具 {name} 不存在,发送 .ag.func 查看全部工具"
        if minutes is None:
            cls._disabled[name] = cls.PERMANENT
            cls._save_disabled()
            return f"工具 {name} 已禁用,直到手动启用"
        until = time.time() + minutes * 60.0
        cls._disabled[name] = until
        cls._save_disabled()
        label = duration_text or f"{minutes:g}分钟"
        return f"工具 {name} 已禁用 {label},到期自动恢复"

    @classmethod
    def enable_tool(cls, name: str) -> str:
        """启用被禁用的工具;未禁用时给出友好提示。"""
        if cls._tools.get(name) is None:
            return f"工具 {name} 不存在,发送 .ag.func 查看全部工具"
        if not cls.is_disabled(name):
            return f"工具 {name} 当前未被禁用"
        cls._disabled.pop(name, None)
        cls._save_disabled()
        return f"工具 {name} 已启用"

    @classmethod
    def register(
        cls,
        name: str,
        desc: str,
        perm: str,
        scenes: tuple[str, ...],
        instance: Any,
        method: Callable[..., Any],
        release: bool = False,
        group: str = "general",
        main_visible: bool = True,
        sub_visible: bool = True,
    ) -> None:
        hints = get_type_hints(method)
        sig = inspect.signature(method)
        properties: dict[str, Any] = {}
        required: list[str] = []
        for pname, p in sig.parameters.items():
            if pname in ("self", "ctx"):
                continue
            anno = hints.get(pname, Any)
            optional = _is_optional(anno)
            properties[pname] = annotation_to_schema(_unwrap_optional(anno))
            if p.default is inspect.Parameter.empty and not optional:
                required.append(pname)
        cls._tools[name] = ToolRegistration(
            name=name,
            instance=instance,
            method=method,
            perm=perm,
            scenes=scenes,
            desc=desc or (inspect.getdoc(method) or "").strip(),
            schema={"type": "object", "properties": properties},
            required=required,
            hints=hints,
            release=release,
            group=group,
            main_visible=main_visible,
            sub_visible=sub_visible,
        )

    @classmethod
    def schema(cls, role: str = "main") -> list[dict[str, Any]]:
        """按角色返回可见工具的 OpenAI schema(禁用工具仍提供,由提示词标注可用性,dispatch 拦截调用)。"""
        return [t.serialize_openai() for t in cls._tools.values() if t.visible_for(role)]

    @classmethod
    async def dispatch(cls, name: str, params: dict[str, Any], ctx: "ToolContext") -> Any:
        reg = cls._tools.get(name)
        if reg is None:
            raise NotImplementedError(f"工具类型 {name} 非法")
        until = cls.disabled_until(name)
        if until is not None:
            if until == cls.PERMANENT:
                return f"工具 {name} 已被禁用,只能由主人手动启用"
            remain = max(0, int(until - time.time()))
            if remain < 60:
                readable = f"约 {remain} 秒后"
            elif remain < 3600:
                readable = f"约 {remain // 60} 分 {remain % 60:02d} 秒后"
            elif remain < 86400:
                readable = f"约 {remain // 3600} 小时 {(remain % 3600) // 60:02d} 分后"
            else:
                readable = f"约 {remain // 86400} 天 {(remain % 86400) // 3600} 小时后"
            return f"工具 {name} 已被禁用,{readable} 自动恢复"
        if not reg.visible_for(ctx.role):
            return f"调用不合法：工具 {name} 不向当前角色({ctx.role})开放"
        if PERM_LEVEL[reg.perm] > PERM_LEVEL[ctx.perm_group]:
            return f"调用不合法：工具 {name} 需要 {reg.perm} 权限，当前为 {ctx.perm_group}"
        if ctx.ev_type not in reg.scenes:
            return f"调用不合法：工具 {name} 不适用于当前场景 {ctx.ev_type}"
        try:
            kwargs = reg.inject_params(params)
        except ToolParamError as e:
            return repr(e)
        result = await reg.method(ctx, **kwargs)
        if reg.release:
            ctx.release_requested = True
        return result


def tool(
    name: str | None = None,
    desc: str = "",
    perm: str = "member",
    scenes: tuple[str, ...] = ("group", "private", "system"),
    release: bool = False,
    group: str = "general",
    main_visible: bool = True,
    sub_visible: bool = True,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        cast(Any, func).__agent_tool__ = (
            name or func.__name__,
            desc,
            perm,
            scenes,
            release,
            group,
            main_visible,
            sub_visible,
        )
        return func

    return decorator


class AgentToolBase:
    """工具基类:子类中的 `@tool` 方法会被自动收集注册。"""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        instance = cls()
        for _, attr in inspect.getmembers(cls):
            spec = getattr(attr, "__agent_tool__", None)
            if spec is None:
                continue
            name, desc, perm, scenes, release, group, main_visible, sub_visible = spec
            ToolRegistry.register(
                name, desc, perm, scenes, instance, getattr(instance, name), release, group, main_visible, sub_visible
            )


# --------------------------------------------------------------------------- #
# 工具上下文
# --------------------------------------------------------------------------- #


@dataclasses.dataclass
class ToolContext:
    actions: Any  # listener.Actions
    ev_type: str  # group / private / system
    scene_id: int
    perm_group: str = "member"  # member / whitelist / bot_owner
    principal_id: int | None = None  # 触发者 QQ
    self_id: int | None = None  # bot 自身 QQ
    runtime: Any = None  # Agent 核心暴露的受限接口
    release_requested: bool = False  # 由 release=True 的工具置位:本轮处理应结束(长程任务交给后台)
    role: str = "main"  # main / sub —— 决定工具可见性(QQ 操作、sub_reply 不向 SubAgent 开放;sub_report 仅 SubAgent)

    async def create_msg(self, raw_mess: Any) -> common.Message:
        new_mess: list[Any] = []
        for j in raw_mess:
            seg_type = j.get("seg")
            if seg_type is None:
                raise RuntimeError("请重新生成")
            match seg_type:
                case "text":
                    new_mess.append(segments.Text(j.get("text")))
                case "at":
                    new_mess.append(segments.At(j.get("qq")))
                case "reply":
                    new_mess.append(segments.Reply(j.get("id")))
                case "image":
                    file = j.get("file")
                    if not file:
                        raise RuntimeError("图片段缺少 file")
                    if not file.startswith(("http", "file:", "base64:")):
                        # 本地路径:校验存在并转 file:// 绝对路径(不用 MediaSeg.build,
                        # hyperot 1.0.0 的 build 对绝对路径分支用无参构造会崩)
                        if not os.path.isfile(file):
                            raise RuntimeError(f"图片文件不存在或无法识别: {file}")
                        file = "file://" + os.path.abspath(file)
                    img = segments.Image(file=file)
                    url = j.get("url")
                    if url:
                        img.url = url
                    new_mess.append(img)
                case _:
                    raise NotImplementedError(f"消息类型 {seg_type} 非法：{raw_mess}")
        return common.Message(*new_mess)


ToolRegistry._load_disabled()
