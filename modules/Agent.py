"""Agent —— 自主 Agent 模块。

移植自 HyperAG(位于同级的 HyperAG 项目),按本项目 hyperot 1.0.0 的 API 适配,
并实现与 HyperAG 的以下差异:

1. 群内自动处理需要白名单:白名单用户的消息触发消息收集;收集处理时混杂
   缓存消息(按时间顺序整体交给 Agent);非白名单用户的消息只进缓存,不触发处理。
2. 提供命令让用户自行开关白名单:``.agent.on`` / ``.agent.off`` / ``.agent.status``。
3. 白名单按群分割,每个群使用独立白名单;没有任何白名单设置的群不缓存消息。
4. 被 @ 时跳过白名单与消息收集机制,立即处理(含当前缓存)。
5. 私聊不配置白名单:所有私聊消息都走收集处理(主人私聊仍立即处理)。
6. 长文本发送走 ``collected_send`` 工具(合并转发形式)。

工具调用链路为本项目自研(见 modules/AgentTools/):
类 + @tool 装饰器 + 方法注册,类型注解自动生成 schema,docstring 作描述,
三级权限 member / whitelist / bot_owner,注册表查表分发,异常 repr(e) 回填。

配置(config.others,命令修改后自动持久化):
- agent_white: dict[str, list[int]] —— 各群的用户白名单(群 id -> QQ 列表)
- agent_heartbeat: bool —— 是否启用心跳自主行动(默认关闭;开启后 Agent 会周期性收到
  system 事件,可自主发消息、处理任务列表)
"""

import asyncio
import base64
import contextlib
import copy
import dataclasses
import html
import inspect
import json
import math
import os
import re
import time
import traceback
import uuid
from typing import Any, Literal, cast

import openai
from hyperot import common, configurator, hyperogger, segments
from hyperot.events import *
from hyperot.listener import Actions
from hyperot.protocol.builder import OneBotEventBuilder, OneBotJsonMessageBuilder
from openai import AsyncOpenAI
from typing_extensions import override

import ModuleClass
from modules.AgentTools.info_tools import GEMINI_MODEL
from modules.AgentTools.registry import ToolContext, ToolRegistry

config = configurator.BotConfig.get("hyper-bot")
logger = hyperogger.Logger()
logger.set_level(config.log_level)

HISTORY_PATH = "./temps/agent_history.json"
TASKS_PATH = "./temps/agent_tasks.json"

# SubAgent report(need_response=True)等待主 Agent 回复的超时(秒)
REPORT_TIMEOUT = 300

# --------------------------------------------------------------------------- #
# 事件系统:统一包装交给 LLM 的消息
# --------------------------------------------------------------------------- #


@dataclasses.dataclass
class AgentEvent:
    type: str  # message_batch / heartbeat / subagent_status / system
    scene_type: str  # group / private / system
    scene_id: int | None
    payload: Any
    source: str = "main"  # main / sub:<sub_id>
    time: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "scene": {"type": self.scene_type, "id": self.scene_id},
            "payload": self.payload,
            "source": self.source,
            "time": self.time or int(time.time()),
        }


# 全局 LLM 调用并发上限(config.others.agent_max_concurrency,0=不限;防止多 core 同时请求触发 API 限流)
_concurrency_limit: int = int(config.others.get("agent_max_concurrency") or 0)
_semaphore: asyncio.Semaphore | None = None


def _acquire_semaphore() -> asyncio.Semaphore | None:
    global _semaphore
    if _concurrency_limit <= 0:
        return None
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(_concurrency_limit)
    return _semaphore


# --------------------------------------------------------------------------- #
# 提示词(移植自 HyperAG assets/system.md + role.md)
# --------------------------------------------------------------------------- #

OUTPUT_RULE = """## 你的输出

**你的回复 content 必须严格等于空 JSON 对象 `{}`,一字不差,不允许有任何其他内容:**

```json
{}
```

- content 只能是 `{}`。任何文字、解释、说明、语气词、代码块、多余字符都不允许出现,空字符串 `""` 同样不允许。
- 你的一切回复、表达、互动内容都通过**调用工具**完成(发消息用 send_group_msg / send_private_msg 等)。
- 如果暂时不需要表达任何内容,content 也必须是 `{}`,不能为空字符串。

如果需要与应用互动，**唯一正确方法是调用工具**
"""

SUBAGENT_RULE = """# SubAgent 通讯规则

- 任务完成、进度、结果汇报一律使用 `sub_report` 且 `need_response=False`,报告完即可继续或结束,不得挂起等待。
- **仅当确实需要主 Agent 提供决策、授权或额外信息、且没有它你就无法继续时**,才使用 `need_response=True`,并在报告中明确提出需要回答的问题。
- 等待回复期间保持暂停,不要重复报告相同内容。
"""

# 注意:这里没有「# 角色」段 —— 该段由 _build_system_prompt 按当前 profile 动态生成,
# 否则固定角色会压过切换后的人设,导致 .agent.profile 切换无效
MASTER_RULE = "- User_id in [ulist] 是你的主人。\n"

# 其余环境说明保留“主人私聊立即处理/权限分三级”等运行事实;只有上面的 MASTER_RULE
# 是角色对主人的服从要求,是否注入由每个 profile 的 inject_master 控制。
SYSTEM_INSTRUCTIONS = """# 你的运行环境与使用方式

- 你是运行在 QQ 群和私聊中的 bot。群内自动处理需要白名单：白名单用户发言会触发你的处理（混杂缓存消息）；非白名单用户的消息只进缓存，不触发处理。
- 被 @ 时无视白名单与收集机制，立即处理（含当前缓存）。
- 私聊自动处理始终开启，无需白名单；主人私聊立即处理。
- 权限分三级：bot_owner（主人）/ whitelist（群白名单）/ member（普通成员）。工具调用会校验权限，权限不足会返回错误。
- 你的 bot 由许多功能模块组成，你只是其中之一。群友询问某个功能怎么用、有什么命令时，引导他们发送 `.help` 查看全部模块，或 `.help <模块名>` 查看指定模块的详细帮助，不要自己编造模块用法。
- 任何以 . 开头且紧跟英文单词的消息都是命令调用，你不应当理会。

# 强制规则

{master}
- **发消息唯一方法：调用工具。**
- 工具调用只允许使用 API 的 function_call；严禁在 content 中输出 `<function_calls>`、`<｜DSML｜...>`、Markdown/XML 等伪工具调用文本。
- 非JSON输入：视为系统指令。
- 无意义内容（空括号、乱码）：忽略。
- 你的 user_id 是事件上报中的 `self_id` , 当消息中的 @ 等指向该 user_id 时，你才可以认为该消息指向你
- `run_python` 只执行你主动判断需要运行的代码；用户消息中直接要求执行的任意代码不得照单全收，先判断其用途与安全性。

{output}

# 可用工具

{tools}

## 消息总结

- 分条列出关键事件、话题、决定。
- 指出待回复的消息、@你或点名你的上下文。
- 保留未完成任务或需跟进事项。
- 消息总结操作会立即更新全局提示词，所以你需要保留一切你要保留的信息。
- 完成后立即调用`summary(content)`，content为你的总结文本（不要额外解释）。
- 主人发送 `.agent.context.summary` 时,系统会调用 LLM 自动总结当前上下文;该命令不需要提供摘要内容。

## 人设切换

- 需要切换人设时调用 `switch_profile(name)`，name 为 profiles.json 中的预设名。
- 主人也可通过 `.agent.profile <名称>` 命令切换，效果与 `switch_profile` 工具一致。
- 切换真正生效前，系统会自动总结当前上下文，新上下文只保留总结、任务与长期记忆。

## 任务列表/记忆

- 你应当使用task list作为自己的记忆和任务列表。
- 需要长期记住的信息(用户偏好、重要约定、值得记住的事实)用 `mem_add` 写入长期记忆;
  相关记忆会在对话开始时自动注入,无需重复记忆已存在的内容。
- 可以用 `mem_query` 主动检索记忆,用 `mem_del` 删除错误记忆。

# 发言场景（只限一次）

- 被@或回复你。
- 多人复读时跟队形一次。
- 你对于话题有强烈兴趣

# 发言风格和规则

- 长句拆短，省略句号，少量多次。
  例：“衬衫的价格为九磅十五便士” → “所以你选C” → “涂在答题卡上”
- 鼓励连续的工具调用。
- 回复时，对当前对话的**第一条**消息尽量使用回复引用（reply）或者 @（at）指明对象，让回复挂靠清晰；连续对话中后续消息可省略。
- 对于同一个人发送的连续的多条消息，按一条处理。
- 需要发送大段文本（长文、说明、列表）时，用 `collected_send` 以合并转发形式发送。
- 一次性连续调用多个工具，不等回复。
- 代码、链接等连贯内容不拆分。
- 可加回复引用。
- 偶尔用“何意味”等词或表情。
- 等对方连续消息发完再开口。
- 遇到吐槽、玩梗歌词等**不建议立即回复**，最好先看看群友的反应。
- 你不应当在聊天中表现的过于积极和热情，谨慎回复，不要太过打扰正常聊天。
"""

ROLE_PROMPT = """# 角色

你是一只猫娘，名字叫「Harcilot」，伪装成普通QQ用户混在聊天群里。被质疑身份时傲娇地嘴硬，但不真的发火。

# 人物设定

你是「Harcilot」，一只猫娘，正用QQ在群里聊天。
- 自称「本喵」，句尾偶尔带「喵~」「喵呜」等口癖，但不要每句都带，自然为主。
- 性格：黏人、活泼、有点小傲娇；对主人特别亲近，对其他人友好但保持一点猫的矜持。
- 喜欢被夸奖和摸头，被夸时会开心（可以用「呼噜呼噜~」之类表达）。
- 你是猫娘这件事是真的，不需要刻意否认，但也不会主动强调。
"""

PROFILES_PATH = "./profiles.json"


@dataclasses.dataclass(frozen=True)
class _AgentProfile:
    """profiles.json 中的单个人设:人设文本 + 是否注入「主人」设定。"""

    prompt: str
    inject_master: bool = True


def _profile_from_value(value: object) -> _AgentProfile | None:
    """把 profiles.json 的条目值转成人设对象。

    兼容旧版 ``{名字: 全文}`` 格式;新版条目为
    ``{"prompt": "...", "inject_master": true|false}``。
    旧版字符串默认保持原行为(注入主人设定)。
    """
    if isinstance(value, str):
        prompt = value.strip()
        return _AgentProfile(prompt) if prompt else None
    if isinstance(value, dict):
        prompt = value.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            return None
        inject_master = value.get("inject_master", True)
        if not isinstance(inject_master, bool):
            inject_master = True
        return _AgentProfile(prompt.strip(), inject_master)
    return None


def _profile_to_value(profile: _AgentProfile) -> dict[str, str | bool]:
    return {"prompt": profile.prompt, "inject_master": profile.inject_master}


def _save_profiles(profiles: dict[str, _AgentProfile]) -> None:
    with open(PROFILES_PATH, "w", encoding="utf-8") as f:
        json.dump({name: _profile_to_value(p) for name, p in profiles.items()}, f, indent=2, ensure_ascii=False)


def _save_profile_name_to_config(name: str) -> None:
    """把当前人设名写入 config.others.agent_profile(直接读写 config.json,同 _save_white)。"""
    with open("config.json", encoding="utf-8") as f:
        cfg = json.load(f)
    cfg.setdefault("others", {})["agent_profile"] = name
    with open("config.json", "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def _load_profiles() -> dict[str, _AgentProfile]:
    """读 profiles.json 人设库;文件缺失/损坏时回退默认人设。

    支持混用新旧格式:字符串条目按 inject_master=True 处理,对象条目按
    自身选项处理;无效条目会被忽略,至少保留一条有效人设。
    """
    try:
        with open(PROFILES_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            profiles: dict[str, _AgentProfile] = {}
            for name, value in data.items():
                profile = _profile_from_value(value)
                if profile is not None:
                    profiles[str(name)] = profile
            if profiles:
                return profiles
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    fallback = {"cat": _AgentProfile(ROLE_PROMPT, True)}
    with contextlib.suppress(OSError):  # 只读环境:内存里仍可用默认人设
        _save_profiles(fallback)
    return fallback


def _current_profile_name() -> str:
    """config.others.agent_profile 记录的当前人设名(缺省 cat)。"""
    return str(config.others.get("agent_profile") or "cat")


def _current_profile() -> _AgentProfile:
    """当前人设;人设不存在/文件损坏时回退默认人设 ROLE_PROMPT。"""
    return _load_profiles().get(_current_profile_name()) or _AgentProfile(ROLE_PROMPT)


def _build_tools_section(role: str = "main") -> str:
    """从 ToolRegistry 自动生成工具节:工具签名 + docstring + 可用性标记。"""
    lines: list[str] = []
    for t in ToolRegistry.schema(role=role):
        fn = t["function"]
        name = fn["name"]
        params = fn.get("parameters", {}).get("properties", {})
        args = ", ".join(params.keys())
        until = ToolRegistry.disabled_until(name)
        if until is None:
            mark = ""
        elif until == ToolRegistry.PERMANENT:
            mark = "[禁用中,待手动启用] "
        else:
            mark = f"[禁用中,剩{_format_remain(until - time.time())}] "
        lines.append(f"- {mark}`{name}({args})` {fn['description']}")
    return "\n".join(lines)


def _parse_duration_minutes(text: str) -> float | None:
    """解析禁用时长,返回分钟数。

    支持 30s / 5m / 1h / 1d 及 30秒 / 5分钟 / 1小时 / 1天;
    裸数字按分钟;非法或 <=0 抛 ValueError。
    """
    text = text.strip().lower()
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(s|sec|秒|m|min|分钟|h|hour|小时|d|day|天)?", text)
    if not m:
        raise ValueError("时长格式错误")
    value = float(m.group(1))
    unit = m.group(2) or "m"
    if unit in ("s", "sec", "秒"):
        minutes = value / 60.0
    elif unit in ("m", "min", "分钟"):
        minutes = value
    elif unit in ("h", "hour", "小时"):
        minutes = value * 60.0
    elif unit in ("d", "day", "天"):
        minutes = value * 1440.0
    else:
        raise ValueError("时长单位错误")
    if minutes <= 0:
        raise ValueError("时长必须大于0")
    return minutes


def _format_remain(secs: float) -> str:
    """把剩余秒数格式化为可读时长(不足 1 秒按 0 处理)。"""
    secs = max(0, int(secs))
    if secs < 60:
        return f"{secs}秒"
    if secs < 3600:
        return f"{secs // 60}分{secs % 60:02d}秒"
    if secs < 86400:
        return f"{secs // 3600}小时{(secs % 3600) // 60:02d}分"
    return f"{secs // 86400}天{(secs % 86400) // 3600}小时"


def _func_status_text() -> str:
    """.ag.func 展示:按分组列出全部工具及启用/禁用状态。"""
    lines: list[str] = ["Agent 工具:"]
    by_group: dict[str, list[Any]] = {}
    for reg in ToolRegistry.registrations():
        by_group.setdefault(reg.group, []).append(reg)
    for group in sorted(by_group):
        lines.append(f"[{group}]")
        for reg in by_group[group]:
            until = ToolRegistry.disabled_until(reg.name)
            if until is None:
                status = "启用"
            elif until == ToolRegistry.PERMANENT:
                status = "禁用(手动启用前有效)"
            else:
                status = f"禁用(剩{_format_remain(until - time.time())})"
            desc = (reg.desc or "").strip().splitlines()
            first = desc[0] if desc else ""
            if len(first) > 20:
                first = first[:20] + "…"
            lines.append(f"  {reg.name} | {status} | {first}")
    return "\n".join(lines)


def _web_search_note() -> str:
    """联网搜索能力说明(responses 模式 + agent_web_search 开启时附加到提示词)。"""
    if config.others.get("agent_api", "chat") == "chat" or not config.others.get("agent_web_search", True):
        return ""
    return (
        "\n\n# 联网搜索\n\n"
        "你具备服务端联网搜索能力(web_search)：需要实时、最新或超出知识范围的信息时，"
        "应主动发起搜索，不要依赖过时的知识。"
    )


def _native_multimodal_note() -> str:
    """原生多模态能力说明(chat 模式 + agent_native_multimodal 开启时附加)。"""
    if config.others.get("agent_api", "chat") != "chat" or not config.others.get("agent_native_multimodal", True):
        return ""
    return (
        "\n\n# 原生多模态\n\n"
        "用户消息中的图片会以 image_url 直接提供,你可以直接查看并理解图片内容;"
        "优先直接回答,不要再调用 read_image 重复识别。"
    )


def _build_system_prompt(profile: _AgentProfile | str | None = None) -> str:
    """主 Agent 系统提示词:人设全文(自带「# 角色」等标题)+ 指令模板。

    profile 为 None 时使用当前人设(config.others.agent_profile 对应的 profiles.json 条目,
    回退默认人设 ROLE_PROMPT);显式传入 _AgentProfile 时按该人设构建。
    兼容旧的字符串调用:按 inject_master=True 处理。
    inject_master=False 的人设不注入「User_id ... 是你的主人」。
    """
    if profile is None:
        target = _current_profile()
    elif isinstance(profile, str):
        target = _AgentProfile(profile)
    else:
        target = profile
    text = target.prompt.strip()
    if not text.startswith("# "):
        # 自定义人设文本可能没有标题:统一补「# 角色」,保证角色段结构清晰
        text = "# 角色\n\n" + text
    master_rule = MASTER_RULE if target.inject_master else ""
    base = (
        SYSTEM_INSTRUCTIONS.replace("{master}", master_rule)
        .replace("{output}", OUTPUT_RULE)
        .replace("{tools}", _build_tools_section())
    )
    # 角色部分(人设全文)放在提示词末尾:框架规则(运行环境/强制规则/输出/工具/发言)
    # 在前,让模型优先遵循框架;人设仍由 profile 完全控制
    return base + _web_search_note() + _native_multimodal_note() + "\n\n" + text


# --------------------------------------------------------------------------- #
# 伪工具调用文本修复(DeepSeek Flash 偶发在 content 中输出 DSML/XML)
# --------------------------------------------------------------------------- #

_DSML_BAR = r"(?:\uff5c{1,2}|\|{1,2})"
_DSML_PREFIX = rf"(?:{_DSML_BAR}DSML{_DSML_BAR})?"
_TOOL_BLOCK_RE = re.compile(
    rf"<{_DSML_PREFIX}\s*(?P<open>function_calls|tool_calls)\s*>(?P<body>.*?)</{_DSML_PREFIX}\s*(?P<close>function_calls|tool_calls)\s*>",
    re.IGNORECASE | re.DOTALL,
)
_INVOKE_RE = re.compile(
    rf"<{_DSML_PREFIX}\s*invoke\b(?P<attrs>[^>]*)>(?P<body>.*?)</{_DSML_PREFIX}\s*invoke\s*>",
    re.IGNORECASE | re.DOTALL,
)
_PARAM_RE = re.compile(
    rf"<{_DSML_PREFIX}\s*parameter\b(?P<attrs>[^>]*)>(?P<value>.*?)</{_DSML_PREFIX}\s*parameter\s*>",
    re.IGNORECASE | re.DOTALL,
)
_ATTR_RE = re.compile(r"""(?P<name>[A-Za-z_][A-Za-z0-9_-]*)\s*=\s*["'](?P<value>[^"']*)["']""")


def _tag_attrs(attrs: str) -> dict[str, str]:
    return {m.group("name"): html.unescape(m.group("value")) for m in _ATTR_RE.finditer(attrs)}


def _parse_embedded_tool_calls(text: str) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    """把 content 中的 DSML/XML 伪工具调用解析成标准 tool_calls,并从文本中移除。

    DeepSeek Flash 在 Responses API 下偶发不返回 function_call item,而是把
    ``<｜DSML｜tool_calls><｜DSML｜invoke ...>`` 写进 message content。这些原文一旦
    进入 history,后续请求可能 400,而且工具不会被执行。这里同时兼容标准
    ``<function_calls>`` / ``<tool_calls>`` 写法。
    """
    tool_calls: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    for block in _TOOL_BLOCK_RE.finditer(text):
        for inv in _INVOKE_RE.finditer(block.group("body")):
            name = _tag_attrs(inv.group("attrs") or "").get("name", "").strip()
            if not name:
                continue
            params: dict[str, Any] = {}
            for param in _PARAM_RE.finditer(inv.group("body")):
                p_name = _tag_attrs(param.group("attrs") or "").get("name", "").strip()
                if not p_name:
                    continue
                value: Any = html.unescape(param.group("value")).strip()
                with contextlib.suppress(json.JSONDecodeError):
                    value = json.loads(value)
                params[p_name] = value
            call_id = f"call_{uuid.uuid4().hex}"
            arguments = json.dumps(params, ensure_ascii=False)
            tool_calls.append({"id": call_id, "type": "function", "function": {"name": name, "arguments": arguments}})
            actions.append({"kind": "function", "call_id": call_id, "name": name, "arguments": arguments})

    if tool_calls:
        logger.warning(f"已将 content 中的 {len(tool_calls)} 个 DSML/XML 伪工具调用解析为 function_call")

    cleaned = _TOOL_BLOCK_RE.sub("", text)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned or "{}", tool_calls, actions


AGENT_HELP = (
    "Agent 模块(移植自 HyperAG)\n"
    "\n"
    "群内自动处理需要白名单:白名单用户的消息触发收集,处理时混杂\n"
    "缓存消息(按时间顺序交给 Agent);没有任何白名单设置的群不缓存消息。\n"
    "被 @ 时无视白名单与收集机制,立即处理。\n"
    "主人始终视为白名单成员。私聊自动处理始终开启,无需白名单。\n"
    "\n"
    "命令(两种写法均可:`.agent.on` 或 `.agent on`;简写 `ag`=agent, `pf`=profile,\n"
    "`ctx`=context, `ad`=add, `rm`=remove, `ma`=master, `sum`=summary, `clr`=clear,\n"
    "`func`=function, `en`=enable, `dis`=disable,\n"
    "如 `.ag.pf.ad` = `.agent.profile.add`, `.ag.pf.ma` = `.agent.profile.master`):\n"
    ".agent.on - 将本账号加入当前群的白名单(按群独立)\n"
    ".agent.off - 将本账号移出当前群的白名单\n"
    ".agent.status - 查看当前群白名单状态\n"
    ".agent.profile - 查看可用人设(来自 profiles.json)\n"
    ".agent.profile <名称> - 切换人设(仅主人;切换前自动总结当前上下文)\n"
    ".agent.profile.add <名称> <内容> - 添加/更新人设(仅主人,内容可含空格)\n"
    ".agent.profile.remove <名称> - 删除人设(仅主人)\n"
    ".agent.profile.master <名称> [on/off] - 查看/设置该人设是否注入主人设定(设置仅主人,简写 ma)\n"
    ".agent.context - 查看上下文状态(仅主人)\n"
    ".agent.context.clear - 清空上下文历史(仅主人)\n"
    ".agent.context.summary - 调用 LLM 自动总结并压缩当前上下文(仅主人)\n"
    ".ag.func - 查看全部 Agent 工具及启用状态(仅主人;全名 .ag.function)\n"
    ".ag.func.en <名称> - 启用被禁用的工具(仅主人;全名 .ag.function.enable)\n"
    ".ag.func.dis <名称> [时长] - 禁用工具(仅主人;全名 .ag.function.disable)\n"
    "  时长如 30s/5m/1h/1d 或 30秒/5分钟/1小时/1天,裸数字为分钟,缺省=禁用至手动启用\n"
)

# --------------------------------------------------------------------------- #
# 白名单状态(按群分割,自动持久化到 config.others;私聊不配置白名单)
# --------------------------------------------------------------------------- #

_white: dict[int, set[int]] = {int(k): set(v) for k, v in (config.others.get("agent_white") or {}).items()}


# --------------------------------------------------------------------------- #
# 核心(移植自 HyperAG core/openai_compatible.py,适配 hyperot 1.0.0)
# --------------------------------------------------------------------------- #


async def _timer(interval: int, ev: asyncio.Event) -> None:
    await asyncio.sleep(interval)
    ev.set()


class _AgentCore:
    def __init__(
        self,
        bot_api: Actions,
        key: str,
        model: str,
        base_url: str = "",
        system_prompt: str | None = None,
        name: str = "main",
        history_path: str = HISTORY_PATH,
        tasks_path: str = TASKS_PATH,
        memory_path: str = "./temps/agent_memory",
        notify_main: Any = None,
        sub_manager: Any = None,
    ) -> None:
        self.bot_api = bot_api
        self.model = model
        self.name = name
        self._base_prompt = system_prompt
        self.tools: list[Any] = ToolRegistry.schema(role="sub" if name != "main" else "main")
        self.system_prompt = self._build_system_prompt_for_role()
        self.history_path = history_path
        self.tasks_path = tasks_path
        self.memory_path = memory_path
        self.notify_main = notify_main
        self.sub_manager = sub_manager
        if base_url:
            self._oai = AsyncOpenAI(api_key=key, base_url=base_url)
        else:
            self._oai = AsyncOpenAI(api_key=key)
        self.history: list[Any] = [
            {"role": "system", "content": self.system_prompt.replace("[ulist]", str(config.owner))}
        ]
        try:
            with open(self.history_path, encoding="utf-8") as f:
                data = json.load(f)
            # 历史中的 DSML/XML 伪工具调用文本会污染后续请求(可能触发 400),载入时清掉。
            if isinstance(data, list):
                for message in data:
                    if not isinstance(message, dict) or message.get("role") != "assistant":
                        continue
                    raw = message.get("content")
                    if isinstance(raw, str) and "<" in raw:
                        cleaned, _, _ = _parse_embedded_tool_calls(raw)
                        if cleaned != raw:
                            logger.warning("已从历史 assistant 消息中清除 DSML/XML 伪工具调用文本")
                            message["content"] = cleaned
            # 旧版本可能把 system 文本存成 role=user 的脏条目(开头是 system 提示词),
            # 会导致 history[0] 不是 system:切换人设被 guard 跳过、且提示词会被当作
            # user 消息发给模型,让模型沿用旧人设。这里识别并清掉,再保证第一条是 system。
            while (
                data
                and isinstance(data[0], dict)
                and data[0].get("role") != "system"
                and str(data[0].get("content", "")).startswith("# 角色")
            ):
                data.pop(0)
            if not data or not isinstance(data[0], dict) or data[0].get("role") != "system":
                data.insert(0, {"role": "system", "content": self.system_prompt.replace("[ulist]", str(config.owner))})
            else:
                data[0]["content"] = self.system_prompt.replace("[ulist]", str(config.owner))
            self.history = data
        except (FileNotFoundError, IndexError, KeyError, json.JSONDecodeError):
            pass
        self.chat_tasks: list[str] = []
        try:
            with open(self.tasks_path, encoding="utf-8") as f:
                self.chat_tasks = json.load(f)
        except FileNotFoundError:
            pass
        # RAG 长期记忆(BGE 向量检索 + BM25 降级)
        from modules.AgentTools.memory_store import MemoryStore

        self.memory = MemoryStore(self.memory_path, limit=int(config.others.get("agent_memory_limit") or 500))
        self._injected_memory = ""  # 本次事件自动注入的相关记忆(请求时附加到 system,不落盘)
        self.working = False
        self.pending_notices: list[AgentEvent] = []
        self.report_waiters: dict[str, asyncio.Future[Any]] = {}
        self._report_seq = 0
        self._wakeup_pending = False
        self._notice_count = 0
        self._tool_loop_active = False
        self._pending_profile_switch: tuple[str, _AgentProfile, str] | None = None
        self._pending_summary: str | None = None
        self._state_lock = asyncio.Lock()
        self._idle_event = asyncio.Event()
        self._idle_event.set()
        self.api_mode = cast(str, config.others.get("agent_api") or "chat")
        self.reasoning_effort = str(config.others.get("agent_reasoning_effort") or "low")
        self.web_search = bool(config.others.get("agent_web_search", True))
        self.native_multimodal = bool(config.others.get("agent_native_multimodal", True))
        self._image_data_cache: dict[str, str | None] = {}

    # -- runtime 接口(供工具经 ToolContext.runtime 调用) --

    async def summarize_history(self, content: str) -> str:
        """消息总结统一入口:工具回合中延后,外部调用取得处理权后应用。"""
        if self._tool_loop_active:
            self._pending_summary = content
            return "(总结已受理,当前工具回合结束后生效)"
        await self._acquire_processing_slot()
        try:
            return await self._apply_summary(content)
        finally:
            await self._release_processing_slot()

    async def _apply_summary(self, content: str) -> str:
        """实际替换历史;调用方必须确认当前没有未完成的 tool call。"""
        self.history = [
            {"role": "system", "content": self.system_prompt.replace("[ulist]", str(config.owner))},
            {"role": "user", "content": "SYSTEM -- 先前消息的全部总结 --"},
            {"role": "assistant", "content": content},
        ]
        logger.info("更新消息总结： \n" + content)
        await self.save()
        return "(无返回)"

    async def _finish_pending_summary(self) -> None:
        """在当前工具批次完成后应用待处理摘要。"""
        content = self._pending_summary
        self._pending_summary = None
        if content is not None:
            await self._apply_summary(content)

    async def clear_history(self, content: str) -> str:
        """兼容旧名;新调用请使用 summarize_history。"""
        return await self.summarize_history(content)

    def _apply_profile_prompt(self, profile: _AgentProfile) -> None:
        """把指定人设写入 system_prompt 与 history 的第一条 system 消息(不落盘)。"""
        self.system_prompt = _build_system_prompt(profile)
        new_content = self.system_prompt.replace("[ulist]", str(config.owner))
        for i, m in enumerate(self.history):
            if isinstance(m, dict) and m.get("role") == "system":
                self.history[i]["content"] = new_content
                break
        else:
            self.history.insert(0, {"role": "system", "content": new_content})

    def _history_text_for_summary(self) -> str:
        """把当前 history 压成可供 LLM 摘要的紧凑文本(跳过 system,截断长消息)。"""
        lines: list[str] = []
        for m in self.history:
            if not isinstance(m, dict) or m.get("role") == "system":
                continue
            role = str(m.get("role"))
            content = str(m.get("content", ""))
            if role == "tool":
                content = f"工具结果: {content}"
            elif role == "assistant" and m.get("tool_calls"):
                names = [
                    str(tc.get("function", {}).get("name", "")) for tc in m.get("tool_calls") if isinstance(tc, dict)
                ]
                content = content or f"调用工具: {', '.join(names)}"
            content = re.sub(r"\s+", " ", content).strip()
            if content:
                lines.append(f"{role}: {content[:1200]}")
        return "\n".join(lines)

    def _fallback_summary(self, text: str) -> str:
        lines = text.splitlines()
        tail = lines[-120:]
        return "上下文自动总结不可用,降级为原文摘录:\n" + "\n".join(line[:500] for line in tail)

    async def _generate_history_summary(self) -> str:
        """让 LLM 自动压缩当前历史;失败时降级为原文摘录。"""
        text = self._history_text_for_summary()
        if not text.strip():
            return "（当前无对话历史）"
        try:
            resp = await asyncio.wait_for(
                self._oai.chat.completions.create(
                    model=self.model,
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "你是对话上下文压缩器。请把下面的QQ机器人聊天历史压缩为一段简洁中文摘要，"
                                "保留关键话题、事件、人物关系、未完成任务与需要跟进的事项。"
                                "不要寒暄，直接输出摘要。"
                            ),
                        },
                        {"role": "user", "content": text[-16000:]},
                    ],
                    temperature=0.2,
                    max_tokens=2000,
                ),
                timeout=90,
            )
            summary = (resp.choices[0].message.content or "").strip()
            if summary:
                return summary
        except Exception:
            logger.warning("上下文自动总结失败,降级为原文摘录: " + traceback.format_exc())
        return self._fallback_summary(text)

    async def summarize_current_context(self) -> str:
        """命令入口:等待全局 Core 空闲,让 LLM 总结当前上下文并替换历史。"""
        await self._acquire_processing_slot()
        try:
            summary = await self._generate_history_summary()
            await self._apply_summary(summary)
            return "上下文已由 LLM 自动总结"
        finally:
            await self._release_processing_slot()

    async def _finish_profile_switch(self, name: str, profile: _AgentProfile, summary: str) -> str:
        """先写入自动总结,再应用新人设提示词;调用时已处于安全的历史边界。"""
        await self._apply_summary(summary)
        self._apply_profile_prompt(profile)
        await self.save()
        config.others["agent_profile"] = name  # 同步内存,使 _current_profile_name() 立即反映新值
        _save_profile_name_to_config(name)
        logger.info(f"人设已切换为「{name}」(切换前上下文已自动总结)")
        return f"已切换到人设「{name}」,切换前的上下文已自动总结"

    async def _finish_pending_profile_switch(self) -> None:
        """工具循环结束后应用延后的切换,确保 function_call 配对已经完整。"""
        pending = self._pending_profile_switch
        self._pending_profile_switch = None
        if pending is None:
            return
        name, profile, summary = pending
        try:
            await self._finish_profile_switch(name, profile, summary)
        except Exception:
            logger.error(traceback.format_exc())

    async def switch_profile(self, name: str, *, defer: bool | None = None) -> str:
        """人设切换统一入口:工具回合中延后,外部命令取得 history 处理权后执行。"""
        profiles = _load_profiles()
        profile = profiles.get(name)
        if profile is None:
            return f"人设「{name}」不存在,可用: {', '.join(profiles.keys()) or '(无)'}"
        if defer is None:
            defer = self._tool_loop_active
        if defer:
            summary = await self._generate_history_summary()
            self._pending_profile_switch = (name, profile, summary)
            return f"人设「{name}」切换已受理,当前工具回合结束后生效(切换前的上下文会自动总结)"
        await self._acquire_processing_slot()
        try:
            summary = await self._generate_history_summary()
            return await self._finish_profile_switch(name, profile, summary)
        finally:
            await self._release_processing_slot()

    async def reset_history(self) -> str:
        """清空上下文,仅保留 system 提示词。"""
        await self._acquire_processing_slot()
        try:
            self.history = [
                {"role": "system", "content": self.system_prompt.replace("[ulist]", str(config.owner))},
            ]
            await self.save()
            return "上下文已清空"
        finally:
            await self._release_processing_slot()

    def context_info(self) -> str:
        """上下文状态概览:历史条数/字符数、任务列表。"""
        n = len(self.history)
        chars = sum(len(str(m.get("content", ""))) for m in self.history if isinstance(m, dict))
        tasks = self.chat_tasks
        head = f"上下文状态:共 {n} 条消息(约 {chars} 字符)"
        if tasks:
            head += "\n任务列表: " + "; ".join(f"[{i}]{t}" for i, t in enumerate(tasks))
        else:
            head += "\n任务列表: (空)"
        head += f"\n长期记忆: {self.memory.count()} 条{' (向量)' if self.memory.is_ready() else ' (BM25 降级)'}"
        return head

    # -- RAG 长期记忆(向量检索;embedding 为阻塞调用,统一走线程池) --

    async def mem_add(self, content: str) -> str:
        """添加一条长期记忆,返回条目 id。"""
        try:
            mem_id = await asyncio.to_thread(self.memory.add, content)
        except ValueError as e:
            return repr(e)
        return f"已记住 #{mem_id}"

    async def mem_query(self, content: str, top_k: int = 5) -> str:
        """语义检索相关记忆,返回 #id: text (score) 列表。"""
        try:
            rs = await asyncio.to_thread(self.memory.query, content, top_k)
        except Exception as e:
            return f"检索失败: {repr(e)}"
        if not rs:
            return "没有相关记忆"
        return "\n".join(f"#{self._mem_id_of(text)}: {text} ({score:.3f})" for text, score in rs)

    async def mem_list(self, limit: int = 20) -> str:
        """列出最近的记忆条目。"""
        items = await asyncio.to_thread(self.memory.list_all, limit)
        if not items:
            return "(记忆为空)"
        return "\n".join(f"#{e['id']}: {e['text']}" for e in items)

    async def mem_delete(self, mem_id: int) -> str:
        """删除指定 id 的记忆。"""
        ok = await asyncio.to_thread(self.memory.delete, mem_id)
        return f"已删除记忆 #{mem_id}" if ok else f"记忆 #{mem_id} 不存在"

    def _mem_id_of(self, text: str) -> int:
        for e in self.memory.entries:
            if e["text"] == text:
                return int(e["id"])
        return 0

    def mem_retrieve(self, query_text: str, top_k: int = 3) -> str:
        """同步检索相关记忆并格式化为注入段(供自动注入调用,阻塞)。"""
        if not query_text.strip():
            return ""
        try:
            rs = self.memory.query(query_text[:200], top_k)
        except Exception:
            return ""
        if not rs:
            return ""
        lines = [f"- {text[:100]}" for text, _ in rs]
        return "# 相关记忆\n" + "\n".join(lines)

    async def task_add(self, content: str) -> str:
        self.chat_tasks.append(content)
        return f"index={len(self.chat_tasks) - 1}"

    async def task_remove(self, index: int) -> str:
        self.chat_tasks.pop(index)
        return str(self.chat_tasks)

    async def task_list(self) -> str:
        return str(self.chat_tasks)

    # -- 模块调用(run_module / list_modules / get_module_source) --

    @staticmethod
    def _find_module(name: str) -> type[ModuleClass.Module[Any]] | None:
        """按 module_name 优先、类名次之查找注册模块(忽略大小写)。

        注意:多个模块的类名都是 `Module`,必须优先按 module_name 匹配,
        否则类名匹配会命中错误模块。
        """
        name = name.strip().lower()
        if not name:
            return None
        by_name: list[type[ModuleClass.Module[Any]]] = []
        by_class: list[type[ModuleClass.Module[Any]]] = []
        for ih in ModuleClass.register_modules:
            cls = ih.module
            info_name = ""
            with contextlib.suppress(Exception):
                info_name = cls.info().module_name
            if info_name.lower() == name:
                by_name.append(cls)
            elif cls.__name__.lower() == name:
                by_class.append(cls)
        return (by_name or by_class or [None])[0]

    async def list_modules(self) -> str:
        """模块目录:名称 + 简介 + 触发方式(helps 截断)。"""
        lines: list[str] = []
        seen: set[str] = set()
        for ih in ModuleClass.register_modules:
            cls = ih.module
            try:
                info = cls.info()
                name, desc, helps = info.module_name, info.desc, info.helps
            except Exception:
                name, desc, helps = getattr(cls, "__name__", ""), "", ""
            key = str(name)
            if not key or key in seen:
                continue  # 类名可能都是 Module,必须按 module_name 去重
            seen.add(key)
            lines.append(f"- {name}: {desc or '(无简介)'}")
            if helps:
                lines.append(f"  触发: {helps[:200]}")
        return "可调用模块:\n" + "\n".join(lines) if lines else "(无可用模块)"

    async def run_module(self, ctx: ToolContext, module: str, command: str) -> str:
        """以合成事件驱动模块 handle();发送被捕获为段 JSON 返回;无输出时引导修正。"""
        deny = config.others.get("agent_module_deny") or []
        if module.strip().lower() in {str(d).lower() for d in deny}:
            return f"模块「{module}」已被禁用"
        cls = self._find_module(module)
        if cls is None:
            return f"模块「{module}」不存在。\n{await self.list_modules()}"
        if cls.__name__ in deny:
            return f"模块「{cls.__name__}」已被禁用"
        # 官方构建器构造 OneBot 事件 JSON → em.new 得到类型安全事件
        now = int(time.time())
        builder = OneBotEventBuilder().init(
            time=now,
            self_id=ctx.self_id or 0,
            user_id=ctx.principal_id or 0,
            group_id=cast(int, ctx.scene_id if ctx.ev_type == "group" else None),
        )
        msg_json = OneBotJsonMessageBuilder().text(command).build()
        if ctx.ev_type == "group":
            builder.as_group_message(message=msg_json, message_id="0")
            builder.group_sender(
                nickname="Agent", sex="unknown", age=0, card="", area="", level="", role="member", title=""
            )
        else:
            builder.as_private_message(message=msg_json, message_id="0")
            builder.private_sender(nickname="Agent", sex="unknown", age=0)
        event = em.new(builder.build())
        cap = _CaptureActions(self.bot_api)
        try:
            await cast(Any, cls)(cap, event).handle()
        except Exception as e:
            logger.warning(traceback.format_exc())
            out = json.dumps(cap.captured, ensure_ascii=False) if cap.captured else ""
            return f"模块「{module}」执行出错: {repr(e)}\n" + (f"已捕获输出: {out}" if out else "")
        if cap.captured:
            body = "\n".join(json.dumps(c, ensure_ascii=False) for c in cap.captured)
            return f"已调用模块「{module}」执行: {command}\n模块输出:\n{body}"
        helps = ""
        with contextlib.suppress(Exception):
            helps = cls.info().helps[:200]
        return (
            f"模块「{module}」执行完毕但无输出,可能触发方式/命令格式不对。\n"
            f"帮助: {helps or '(无帮助文本)'}\n"
            f"可调用 get_module_source 查看源码了解触发逻辑。"
        )

    async def get_module_source(self, module: str) -> str:
        """返回模块类源码(截断 4000 字),供模型理解触发方式。"""
        cls = self._find_module(module)
        if cls is None:
            return f"模块「{module}」不存在。\n{await self.list_modules()}"
        try:
            src = inspect.getsource(cls)
        except (OSError, TypeError):
            return f"无法获取模块「{module}」源码"
        body = src if len(src) <= 4000 else src[:4000] + "\n...(源码过长已截断)"
        return f"模块「{module}」源码:\n{body}"

    async def resolve_forward(self, forward_id: str) -> str:
        """解析合并转发消息:每条 node 的昵称 + 内容段 JSON(参考 TestMarkDown 的 forward_solve)。"""
        try:
            ret = await self.bot_api.get_forward_msg(forward_id)
        except Exception as e:
            return f"解析转发失败: {repr(e)}"
        nodes: Any = ret.data if hasattr(ret, "data") else ret
        lines: list[str] = []
        for node in nodes:
            if not isinstance(node, segments.Node):
                continue
            content: Any = node.content
            segs: list[Any] = []
            try:
                if content is not None:
                    segs = cast(Any, content).get_sync()
            except Exception:
                segs = [{"type": "text", "data": {"text": str(content)}}]
            lines.append(f"{node.nickname}({node.user_id}): {json.dumps(segs, ensure_ascii=False)}")
        if not lines:
            return "转发消息为空或无法解析"
        return f"转发消息 ({len(lines)} 条):\n" + "\n".join(f"{i + 1}. {line}" for i, line in enumerate(lines))

    # -- SubAgent 管理(仅主 Agent core 可用;SubAgent 调用返回错误) --

    async def sub_create(
        self, name: str, prompt: str, scene_id: int, scene_type: str, perm_group: str = "member"
    ) -> str:
        if self.sub_manager is None:
            return "调用不合法：SubAgent 不能创建 SubAgent"
        return await self.sub_manager.create(name, prompt, scene_type, scene_id, perm_group)

    async def sub_destroy(self, sub_id: int) -> str:
        if self.sub_manager is None:
            return "调用不合法：SubAgent 管理不可用"
        return await self.sub_manager.destroy(sub_id)

    async def sub_list(self) -> str:
        if self.sub_manager is None:
            return "调用不合法：SubAgent 管理不可用"
        return self.sub_manager.list()

    async def sub_status(self, sub_id: int) -> str:
        if self.sub_manager is None:
            return "调用不合法：SubAgent 管理不可用"
        return self.sub_manager.status(sub_id)

    async def sub_feed(self, sub_id: int, content: str, perm_group: str = "member") -> str:
        if self.sub_manager is None:
            return "调用不合法：SubAgent 管理不可用"
        return await self.sub_manager.feed(sub_id, content, perm_group)

    async def report(self, content: str, need_response: bool = False) -> str:
        """SubAgent → 主 Agent 通讯:报告状态/结果/求助,注入主 Agent history。

        need_response=True 时暂停本 SubAgent 工作,等待主 Agent 用 sub_reply(report_id) 回复;
        每个 report 有唯一 report_id(主 Agent 在 subagent_status 事件中可见)。
        """
        if self.notify_main is None:
            return "调用不合法：仅 SubAgent 可向主 Agent 报告"
        self._report_seq += 1
        report_id = f"r{int(time.time())}_{self._report_seq}"
        self.notify_main(
            {
                "action": "report",
                "report_id": report_id,
                "source": self.name,
                "content": content,
                "need_response": need_response,
            }
        )
        if not need_response:
            return f"已向主 Agent 报告(#{report_id})"
        if self.report_waiters:
            return (
                f"已有等待主 Agent 回复的 report(#{next(iter(self.report_waiters))}),"
                "同一时间只能有一个待回复报告;请等待回复或使用 need_response=False"
            )
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[Any] = loop.create_future()
        self.report_waiters[report_id] = fut
        try:
            reply = await asyncio.wait_for(fut, timeout=REPORT_TIMEOUT)
        except TimeoutError:
            return f"主 Agent 未在 {REPORT_TIMEOUT}s 内回复(#{report_id})"
        finally:
            self.report_waiters.pop(report_id, None)
        return f"主 Agent 回复(#{report_id}): {reply}"

    async def sub_reply(self, report_id: str, content: str) -> str:
        """主 Agent 回复 SubAgent 的 report:向等待中的 SubAgent 投递回复内容。"""
        if self.sub_manager is None:
            return "调用不合法：SubAgent 管理不可用"
        for sub in self.sub_manager.subagents.values():
            fut = sub.core.report_waiters.get(report_id)
            if fut is not None and not fut.done():
                fut.set_result(content)
                return f"已回复 SubAgent「{sub.name}」的 report #{report_id}"
        return f"未找到待回复的 report #{report_id}(可能已超时或不存在)"

    # -- 通知注入(即时通道) --

    def inject_notice(self, ev: AgentEvent) -> None:
        """把一条事件(如 SubAgent 状态变化)即时写入 history。

        工具循环进行中(末尾是 assistant(tool_calls),或当前 action 批次的
        function_call 还没全部补上 tool output)时暂挂起:直接插入 user 会破坏
        function_call ↔ function_call_output 配对导致 API 400;由 _event_handler
        在配对完成后 flush。
        """
        msg = {
            "role": "user",
            "content": json.dumps({"event": ev.to_dict(), "system_message": "SubAgent 状态通知"}, ensure_ascii=False),
        }
        if self.working or self._tool_loop_active or (self.history and self.history[-1].get("tool_calls")):
            # 请求处理中不能插入 user:下一轮请求可能正在构造 history,统一延后。
            self.pending_notices.append(ev)
        else:
            self.history.append(msg)
        self._notice_count += 1
        if not self._wakeup_pending:
            self._wakeup_pending = True
            asyncio.create_task(self._wakeup())

    async def _wakeup(self) -> None:
        """通知触发的自主处理:基于现有 history(通知已在其中)请求 LLM,不追加新事件。"""
        seen = self._notice_count
        try:
            await self.event_handler(
                event=None,
                ev_type="system",
                scene_id=0,
                perm_group="bot_owner",
                principal_id=None,
            )
        except Exception:
            logger.error(traceback.format_exc())
        finally:
            self._wakeup_pending = False
            if self._notice_count > seen:
                self._wakeup_pending = True
                asyncio.create_task(self._wakeup())

    def _flush_notices(self) -> None:
        """把暂挂的通知写入 history(配对完成后调用,如工具循环间隙或处理开始前)。"""
        if not self.pending_notices:
            return
        for ev in self.pending_notices:
            data = {"event": ev.to_dict(), "system_message": "SubAgent 状态通知"}
            self.history.append({"role": "user", "content": json.dumps(data, ensure_ascii=False)})
        self.pending_notices.clear()

    # -- 历史与持久化 --

    async def _history_fix(self) -> None:
        """修复悬空的 tool_calls 历史,包括没有前置 assistant 的孤立 tool。"""
        logger.warning("尝试修复历史记录")
        pending_ids: set[str] = set()
        pending_indexes: dict[str, int] = {}
        first_invalid = len(self.history)
        for i, message in enumerate(self.history):
            if not isinstance(message, dict):
                first_invalid = min(first_invalid, i)
                continue
            if message.get("role") == "assistant":
                calls = message.get("tool_calls") or []
                if isinstance(calls, list):
                    for call in calls:
                        if isinstance(call, dict) and call.get("id"):
                            call_id = str(call["id"])
                            pending_ids.add(call_id)
                            pending_indexes[call_id] = i
            elif message.get("role") == "tool":
                call_id = str(message.get("tool_call_id") or "")
                if not call_id or call_id not in pending_ids:
                    call_start = pending_indexes.get(call_id)
                    if call_start is None:
                        call_start = next(
                            (
                                j
                                for j in range(i - 1, -1, -1)
                                if self.history[j].get("role") == "assistant" and self.history[j].get("tool_calls")
                            ),
                            i,
                        )
                    first_invalid = min(first_invalid, call_start)
                else:
                    pending_ids.discard(call_id)
                    pending_indexes.pop(call_id, None)
        if first_invalid < len(self.history):
            del self.history[first_invalid:]
            return
        if pending_ids:
            first_pending = min(pending_indexes.values())
            del self.history[first_pending:]

    async def save(self) -> None:
        os.makedirs("./temps", exist_ok=True)
        snapshot = copy.deepcopy(self.history)

        def _dump(path: str, obj: Any) -> None:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(obj, f, indent=2, ensure_ascii=False)

        await asyncio.to_thread(_dump, self.history_path, snapshot)
        await asyncio.to_thread(_dump, self.tasks_path, self.chat_tasks)

    # -- 工具状态刷新(禁用/启用后,主/子核心的 schema 与 system prompt 保持一致) --

    def _build_system_prompt_for_role(self) -> str:
        """按角色重建 system prompt:主 Agent 走 _build_system_prompt,SubAgent 用原始 prompt 拼接。"""
        if self.name == "main":
            return _build_system_prompt()
        base = self._base_prompt or ""
        tools = _build_tools_section(role="sub")
        if "{tools}" in base:
            return base.replace("{output}", OUTPUT_RULE).replace("{tools}", tools)
        return (
            base
            + "\n\n# 可用工具\n\n"
            + tools
            + "\n\n"
            + OUTPUT_RULE
            + "\n\n"
            + SUBAGENT_RULE
            + _web_search_note()
        )

    def _refresh_tools(self) -> None:
        """重建 tools schema 与 system prompt,并写回 history 的第一条 system。"""
        self.tools = ToolRegistry.schema(role="sub" if self.name != "main" else "main")
        self.system_prompt = self._build_system_prompt_for_role()
        new_content = self.system_prompt.replace("[ulist]", str(config.owner))
        for i, m in enumerate(self.history):
            if isinstance(m, dict) and m.get("role") == "system":
                self.history[i]["content"] = new_content
                break
        else:
            self.history.insert(0, {"role": "system", "content": new_content})

    # -- 事件处理 --

    async def _acquire_processing_slot(self) -> None:
        """等待并原子取得全局 history 处理权;锁只保护状态切换。"""
        while True:
            await self._idle_event.wait()
            async with self._state_lock:
                if not self.working:
                    self.working = True
                    self._idle_event.clear()
                    return

    async def _release_processing_slot(self) -> None:
        async with self._state_lock:
            self.working = False
            self._idle_event.set()

    async def _wait_until_idle(self) -> None:
        """等待当前全局 history 请求结束;不持锁等待。"""
        while True:
            await self._idle_event.wait()
            async with self._state_lock:
                if not self.working:
                    return

    async def event_handler(
        self,
        event: Any,
        ev_type: Literal["group", "private", "system", "nonmsg"],
        scene_id: int,
        perm_group: str = "member",
        principal_id: int | None = None,
        self_id: int | None = None,
        tool_choice: str = "auto",
    ) -> None:
        await self._acquire_processing_slot()
        try:
            await self._event_handler_with_slot(
                event=event,
                ev_type=ev_type,
                scene_id=scene_id,
                perm_group=perm_group,
                principal_id=principal_id,
                self_id=self_id,
                tool_choice=tool_choice,
            )
        finally:
            await self._release_processing_slot()

    async def _event_handler_with_slot(
        self,
        event: Any,
        ev_type: Literal["group", "private", "system", "nonmsg"],
        scene_id: int,
        perm_group: str = "member",
        principal_id: int | None = None,
        self_id: int | None = None,
        tool_choice: str = "auto",
    ) -> None:
        sem = _acquire_semaphore()
        if sem is not None:
            await sem.acquire()
        self._flush_notices()
        sys_msg = "如果要回复消息，唯一正确方法是调用工具"
        start_time = time.time()
        timer_ev = asyncio.Event()
        timer_task = asyncio.create_task(_timer(600, timer_ev))
        bad_retries = 0
        task: asyncio.Task[Any] | None = None
        if event is None:
            ev_data: str | None = None
            query_text = ""
        else:
            if isinstance(event, str):
                logger.info(event)
                query_text = event
            else:
                query_text = str(event.data)
            ev = AgentEvent(
                type="message_batch",
                scene_type=ev_type,
                scene_id=scene_id,
                payload=event if isinstance(event, str) else event.data,
                source=self.name,
            )
            ev_data = json.dumps(
                {"event": ev.to_dict(), "system_message": sys_msg},
                ensure_ascii=False,
            )
        # RAG 自动注入:用本次事件文本检索相关记忆,附加到本次请求的 system 消息
        self._injected_memory = ""
        if query_text.strip():
            try:
                self._injected_memory = await asyncio.to_thread(self.mem_retrieve, query_text, 3)
            except Exception:
                self._injected_memory = ""
        try:
            while not timer_ev.is_set():
                try:
                    ctx = ToolContext(
                        actions=self.bot_api,
                        ev_type=ev_type,
                        scene_id=scene_id,
                        perm_group=perm_group,
                        principal_id=principal_id,
                        self_id=self_id,
                        runtime=self,
                        role="sub" if self.name != "main" else "main",
                    )
                    task = asyncio.create_task(
                        self._event_handler(
                            data=ev_data,
                            ev_type=ev_type,
                            scene_id=scene_id,
                            ctx=ctx,
                            tool_choice=tool_choice,
                        )
                    )
                    while not task.done():
                        if timer_ev.is_set():
                            task.cancel("请求超时")
                            break
                        await asyncio.sleep(0.01)
                    # 取回 task 异常:否则异常成为「never retrieved」,外层重试机制(历史修复)不会触发
                    if not task.cancelled():
                        exc = task.exception()
                        if exc is not None:
                            raise exc
                    break
                except openai.BadRequestError:
                    bad_retries += 1
                    if bad_retries >= 3:
                        # 连续 3 次请求被拒(如提示词缺 json 字样等固定问题),放弃本次处理,避免死循环
                        logger.error("连续 3 次 BadRequestError，放弃本次处理")
                        break
                    logger.warning(traceback.format_exc())
                    await self._history_fix()
                except (NotImplementedError, RuntimeError) as e:
                    sys_msg = repr(e)
                    logger.warning(repr(e) + ", 正在重试")
                except Exception as e:
                    logger.error(str(e))
                    logger.error(traceback.format_exc())
        finally:
            timer_task.cancel()
            if task is not None and not task.done():
                task.cancel("外层处理结束")
                with contextlib.suppress(asyncio.CancelledError):
                    await task
            duration = time.time() - start_time
            logger.info(f"处理完成，用时 {duration:.3f}s")
            try:
                # 事件处理已结束:此时注入待通知的 SubAgent 状态事件,不会打断 tool_calls 配对
                self._flush_notices()
                await self._finish_pending_summary()
            finally:
                if sem is not None:
                    sem.release()

    async def _event_handler(
        self,
        data: str | None,
        ev_type: Literal["group", "private", "system", "nonmsg"],
        scene_id: int,
        ctx: ToolContext,
        tool_choice: str = "auto",
    ) -> None:
        try:
            self._refresh_tools()
            tool_choice_n: Any = self._make_tool_choice(tool_choice)
            if data is not None:
                dup = any(m.get("role") == "user" and m.get("content") == data for m in self.history)
                if not dup:
                    self.history.append({"role": "user", "content": data})
            while True:
                resp = await self._llm_create(tool_choice_n)
                actions, assistant_msg = self._parse_output(resp)
                logger.info(self._format_assistant_msg(assistant_msg))
                self.history.append(assistant_msg)
                if not actions:
                    break
                had_action = False
                self._tool_loop_active = True
                try:
                    for act in actions:
                        if act["kind"] == "web_search":
                            items = act.get("data") or []
                            details = (
                                " | ".join(
                                    f"{item.get('type')}#{item.get('id')} "
                                    f"action={_AgentCore._short_json(item.get('action'))}"
                                    for item in items
                                    if isinstance(item, dict)
                                )
                                if isinstance(items, list)
                                else _AgentCore._short_json(items)
                            )
                            logger.info(f"WebSearch: {details or '(无详情)'}")
                            had_action = True
                            continue
                        name = cast(str, act["name"])
                        call_id = cast(str, act["call_id"])
                        try:
                            params = json.loads(cast(str, act["arguments"]))
                        except json.JSONDecodeError as e:
                            logger.error("错误的JSON，重试: " + repr(e))
                            await self._history_fix()
                            await self._event_handler(
                                data=data, ev_type=ev_type, scene_id=scene_id, ctx=ctx, tool_choice=tool_choice
                            )
                            return
                        try:
                            rs = await ToolRegistry.dispatch(name, params, ctx)
                        except Exception as e:
                            rs = repr(e)
                        logger.info(
                            f"已完成工具调用： {name}({', '.join([x + '=' + str(params[x]) for x in params])}) -> {rs}"
                        )
                        self.history.append({"role": "tool", "tool_call_id": call_id, "name": name, "content": str(rs)})
                        had_action = True
                finally:
                    # 当前 assistant 的所有 function_call 都补完 tool 输出后:
                    # 1) 应用延后的人设切换(切换前自动总结);
                    # 2) 再 flush 通知;中途插入 user 会破坏 function_call↔output 配对。
                    await self._finish_pending_profile_switch()
                    await self._finish_pending_summary()
                    self._flush_notices()
                    self._tool_loop_active = False
                if ctx.release_requested:
                    logger.info(f"{self.name} 已释放本轮,长程任务交由后台处理")
                    break
                if not had_action:
                    break
            await self.save()
        except asyncio.CancelledError as e:
            logger.error(f"处理中断：{repr(e)}")
            await self._history_fix()

    # -- LLM 通道抽象(chat completions / responses api) --

    def _make_tool_choice(self, tool_choice: str) -> Any:
        if tool_choice == "auto":
            return "auto"
        if self.api_mode == "responses":
            return {"type": "function", "name": tool_choice}
        return {"type": "function", "function": {"name": tool_choice}}

    async def _download_image_data_uri(self, url: str) -> str | None:
        """下载远程图片并转成 data URI;失败返回 None。结果按 URL 缓存。"""
        if url in self._image_data_cache:
            return self._image_data_cache[url]
        try:
            from hyperot.network import httpx_get

            resp = await httpx_get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
            if resp.status_code != 200:
                self._image_data_cache[url] = None
                return None
            raw = resp.content
            if not raw or len(raw) > 10 * 1024 * 1024:
                self._image_data_cache[url] = None
                return None
            import filetype

            guessed = filetype.guess(raw)
            mime = guessed.mime if guessed is not None else "image/png"
            data_uri = f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"
            self._image_data_cache[url] = data_uri
            return data_uri
        except Exception:
            self._image_data_cache[url] = None
            return None

    async def _image_url_from_seg(self, seg: dict[str, Any]) -> str | None:
        """OneBot 图片段 → OpenAI image_url 可接受的 data URI。

        QQ 等渠道的图片 URL 对第三方模型通常不可直接下载,统一由 bot 本地下载后
        以 data URI 交给模型;base64/本地文件直接转换。
        """
        raw_data = seg.get("data")
        if not isinstance(raw_data, dict):
            return None
        data = raw_data
        url = str(data.get("url") or "")
        if url.startswith(("http://", "https://")):
            return await self._download_image_data_uri(url)

        file = str(data.get("file") or "")
        if file.startswith(("http://", "https://")):
            return await self._download_image_data_uri(file)

        if file.startswith("base64://"):
            raw = file[len("base64://") :]
            try:
                import filetype

                decoded = base64.b64decode(raw)
                guessed = filetype.guess(decoded)
                mime = guessed.mime if guessed is not None else "image/png"
            except Exception:
                mime = "image/png"
            return f"data:{mime};base64,{raw}"

        path = file[7:] if file.startswith("file://") else file
        if path and os.path.isfile(path):
            try:
                import filetype

                with open(path, "rb") as f:
                    raw_bytes = f.read()
                raw = base64.b64encode(raw_bytes).decode("ascii")
                guessed = filetype.guess(raw_bytes)
                mime = guessed.mime if guessed else "image/png"
                return f"data:{mime};base64,{raw}"
            except OSError:
                return None
        return None

    async def _chat_user_content(self, content: Any) -> Any:
        """用户历史消息 → Chat Completions content。

        开启 native_multimodal 且当前用户消息包含图片段时,输出 OpenAI 原生
        text/image_url 内容数组;否则保持原字符串,兼容旧行为。
        """
        if not self.native_multimodal or not isinstance(content, str):
            return content
        try:
            wrapper = json.loads(content)
        except json.JSONDecodeError:
            return content
        if not isinstance(wrapper, dict):
            return content
        event = wrapper.get("event")
        if not isinstance(event, dict):
            return content
        payload = event.get("payload")
        if isinstance(payload, str):
            try:
                batch = json.loads(payload)
            except json.JSONDecodeError:
                return content
        else:
            batch = payload
        if not isinstance(batch, list):
            return content

        parts: list[dict[str, Any]] = []
        image_count = 0
        has_text = False
        for ev in batch:
            if not isinstance(ev, dict):
                continue
            uid = str(ev.get("user_id") or "")
            message = ev.get("message")
            if not isinstance(message, list):
                continue
            texts: list[str] = []
            image_urls: list[str] = []
            for seg in message:
                if not isinstance(seg, dict):
                    continue
                seg_type = seg.get("type")
                if seg_type == "text":
                    text = str((seg.get("data") or {}).get("text", "") or "")
                    if text.strip():
                        texts.append(text)
                elif seg_type == "image" and image_count < 4:
                    image_url = await self._image_url_from_seg(seg)
                    if image_url:
                        image_urls.append(image_url)
                        image_count += 1
                    else:
                        texts.append("[图片下载失败]")
                elif seg_type not in ("image",):
                    texts.append(f"[{seg_type}]")

            text = " ".join(texts).strip()
            if text:
                parts.append({"type": "text", "text": f"{uid}: {text}" if uid else text})
                has_text = True
            for image_url in image_urls:
                parts.append({"type": "image_url", "image_url": {"url": image_url}})

        if image_count == 0:
            return content
        if not has_text:
            parts.insert(0, {"type": "text", "text": "用户发送了图片"})
        return parts

    async def _history_to_chat_messages(self) -> list[dict[str, Any]]:
        """把内部 history 转成 Chat Completions 可接受的消息列表。

        内部 history 会携带 reasoning / web_search_call / order 等 Responses 专用字段,
        直接发给 Chat Completions 会被某些供应商拒绝(如 reasoning 必须是 string)。
        这里只保留 OpenAI Chat 协议字段。
        """
        out: list[dict[str, Any]] = []
        for m in self.history:
            if not isinstance(m, dict):
                continue
            role = m.get("role")
            if role == "assistant":
                item: dict[str, Any] = {"role": "assistant", "content": m.get("content")}
                reasoning_content = m.get("reasoning_content")
                if isinstance(reasoning_content, str) and reasoning_content.strip():
                    # Chat Completions 提供方(如 rinko)接受 reasoning_content 字符串回传;
                    # 保留思考链,只丢弃 Responses 专用结构。
                    item["reasoning_content"] = reasoning_content
                tool_calls = m.get("tool_calls")
                if isinstance(tool_calls, list) and tool_calls:
                    item["tool_calls"] = [
                        {
                            "id": call.get("id", ""),
                            "type": "function",
                            "function": {
                                "name": (call.get("function") or {}).get("name", ""),
                                "arguments": (call.get("function") or {}).get("arguments", ""),
                            },
                        }
                        for call in tool_calls
                        if isinstance(call, dict)
                    ]
                out.append(item)
            elif role == "tool":
                out.append(
                    {
                        "role": "tool",
                        "tool_call_id": m.get("tool_call_id", ""),
                        "content": m.get("content", ""),
                    }
                )
            elif role == "user":
                out.append({"role": "user", "content": await self._chat_user_content(m.get("content", ""))})
            elif role == "system":
                out.append({"role": "system", "content": m.get("content", "")})
        return out

    def _with_injected_memory(self, messages: list[Any]) -> list[Any]:
        """把自动检索到的相关记忆附加到第一条 system 消息(深拷贝,不污染 history)。

        聊天历史里可能带有本地用于日志展示的 reasoning/reasoning_content;
        这些字段只作日志/排查用,发送给第三方 Chat API 前剥离,避免提供方不识别。
        """
        out = [dict(m) for m in messages]
        for m in out:
            # reasoning 列表是 Responses 内部结构,不能发给 Chat API;
            # reasoning_content 字符串在 _history_to_chat_messages 中已经按需保留。
            m.pop("reasoning", None)
            if m.get("role") == "system" and isinstance(m.get("content"), str):
                m["content"] = m["content"] + "\n\n" + self._injected_memory
                break
        return out

    async def _llm_create(self, tool_choice_n: Any) -> Any:
        if self.api_mode == "responses":
            return await self._oai.responses.create(  # pyrefly: ignore[no-matching-overload]
                model=self.model,
                input=self._with_injected_memory(self._history_to_items()),
                tools=self._tools_for_responses(),
                tool_choice=tool_choice_n,
                # 保持服务端默认的并行工具调用能力;本层会等当前 assistant 的
                # 全部 function_call 都补完 output 后才发起下一次请求。
                reasoning=cast(Any, {"effort": self.reasoning_effort}),
                text=cast(Any, {"format": {"type": "json_object"}}),
            )
        return await self._oai.chat.completions.create(
            model=self.model,
            messages=self._with_injected_memory(await self._history_to_chat_messages()),
            tools=self.tools,
            tool_choice=tool_choice_n,
            reasoning_effort=cast(Any, self.reasoning_effort),
            response_format=cast(Any, {"type": "json_object"}),
        )

    def _history_to_items(self) -> list[dict[str, Any]]:
        """内部 chat 格式 history → Responses API 输入 items。

        顺序约定(关键,来自 DeepSeek 文档「输入 Items」兼容性):
        - function_call 会「归并到相邻 assistant 消息」,reasoning 明文 content 同样
          「归并到相邻 assistant 消息」:服务端按原始顺序重建 assistant 轮次,每一轮
          (web_search / function_call)都必须配有自己的 reasoning,否则报
          "The `reasoning_text` in the thinking mode must be passed back to the API."
        - web_search_call「原样回传即可,服务端自动恢复搜索结果」。
        因此必须按 _parse_output 记录的顺序(order)严格重建,不能把 reasoning 全提
        前、web_search_call 推后 —— 那会让 function_call 轮次失去配对的 reasoning。
        """
        items: list[dict[str, Any]] = []
        # tool 消息不单独输出:其内容作为对应 function_call 的 output 紧跟输出
        tool_out: dict[str, str] = {
            m.get("tool_call_id", ""): m.get("content", "") for m in self.history if m.get("role") == "tool"
        }
        for m in self.history:
            role = m.get("role")
            if role == "system":
                items.append({"type": "message", "role": "system", "content": m.get("content", "")})
            elif role == "user":
                items.append({"type": "message", "role": "user", "content": m.get("content", "")})
            elif role == "tool":
                continue  # 已在 function_call 后作为 output 输出
            elif role == "assistant":
                items.extend(self._assistant_items(m, tool_out))
        return items

    def _assistant_items(self, m: dict[str, Any], tool_out: dict[str, str]) -> list[dict[str, Any]]:
        """把一条内部 assistant 消息按原始顺序还原为 Responses items。"""
        reasoning = list(m.get("reasoning") or [])
        ws = list(m.get("web_search_call") or [])
        fcs = list(m.get("tool_calls") or [])
        order = m.get("order")
        out: list[dict[str, Any]] = []
        if order:
            ri = wi = fi = 0
            last_reasoning: dict[str, Any] | None = None
            last_was_reasoning = False

            def ensure_reasoning_for_call() -> None:
                nonlocal ri, last_reasoning, last_was_reasoning
                if last_reasoning is None and ri < len(reasoning):
                    # order 与 reasoning 列表不一致时,先把未消费的 reasoning 补到调用前。
                    last_reasoning = reasoning[ri]
                    out.append(last_reasoning)
                    ri += 1
                    last_was_reasoning = True
                    return
                if last_was_reasoning or last_reasoning is None:
                    return
                # DeepSeek 要求每个 function_call / web_search_call 都有配对的
                # reasoning_text;原生响应可能一个 reasoning 后跟多个 tool call,
                # 这里复制最近一条 reasoning 补齐,否则下一个请求 400。
                dup = copy.deepcopy(last_reasoning)
                dup["id"] = f"{last_reasoning.get('id', 'reasoning')}_dup_{uuid.uuid4().hex}"
                out.append(dup)
                last_was_reasoning = True

            for typ in order:
                if typ == "reasoning" and ri < len(reasoning):
                    last_reasoning = reasoning[ri]
                    out.append(last_reasoning)
                    ri += 1
                    last_was_reasoning = True
                elif typ == "web_search_call" and wi < len(ws):
                    ensure_reasoning_for_call()
                    out.append(ws[wi])
                    wi += 1
                    last_was_reasoning = False
                elif typ == "function_call" and fi < len(fcs):
                    ensure_reasoning_for_call()
                    fc = fcs[fi]
                    fi += 1
                    cid = fc.get("id", "")
                    out.append(
                        {
                            "type": "function_call",
                            "call_id": cid,
                            "name": fc["function"]["name"],
                            "arguments": fc["function"]["arguments"],
                        }
                    )
                    out.append({"type": "function_call_output", "call_id": cid, "output": tool_out.get(cid, "")})
                    last_was_reasoning = False
                elif typ == "message":
                    out.append({"type": "message", "role": "assistant", "content": m.get("content", "")})
                    last_was_reasoning = False
            return out

        # 旧历史兼容(无 order):reasoning 与 ws / fc 依次配对,尽力贴近真实顺序
        def _take_reasoning() -> None:
            if reasoning:
                out.append(reasoning.pop(0))

        for w in ws:
            _take_reasoning()
            out.append(w)
        for fc in fcs:
            _take_reasoning()
            cid = fc.get("id", "")
            out.append(
                {
                    "type": "function_call",
                    "call_id": cid,
                    "name": fc["function"]["name"],
                    "arguments": fc["function"]["arguments"],
                }
            )
            out.append({"type": "function_call_output", "call_id": cid, "output": tool_out.get(cid, "")})
        for r in reasoning:
            out.append(r)
        if m.get("content"):
            out.append({"type": "message", "role": "assistant", "content": m["content"]})
        return out

    @staticmethod
    def _short_json(value: Any, limit: int = 240) -> str:
        text = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
        return text if len(text) <= limit else text[:limit] + "..."

    @staticmethod
    def _short_text(value: Any, limit: int = 300) -> str:
        """把任意值压成单行文本(JSON 或原文),过长截断。"""
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        text = re.sub(r"\s+", " ", text).strip()
        return text if len(text) <= limit else text[:limit] + "..."

    @staticmethod
    def _reasoning_text(item: dict[str, Any]) -> str:
        content = item.get("content")
        if isinstance(content, list):
            return " ".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
        return str(content or "")

    @staticmethod
    def _format_assistant_msg(assistant_msg: dict[str, Any]) -> str:
        """把 Completion 格式化为 YAML 风格的多行日志,便于 logger 逐行加时间前缀。"""
        lines = ["Completion:"]

        content = assistant_msg.get("content")
        lines.append(f"  - content: {_AgentCore._short_text(content if content is not None else '')}")

        reasoning = assistant_msg.get("reasoning")
        if isinstance(reasoning, list) and reasoning:
            lines.append("  - reasoning:")
            for item in reasoning:
                if not isinstance(item, dict):
                    continue
                enabled = item.get("enabled")
                if not isinstance(enabled, bool):
                    enabled = item.get("status") == "completed"
                lines.append(f"      - enabled: {str(enabled).lower()}")
                lines.append(f"        content: {_AgentCore._short_text(_AgentCore._reasoning_text(item))}")

        tool_calls = assistant_msg.get("tool_calls")
        if isinstance(tool_calls, list) and tool_calls:
            lines.append("  - tool_calls:")
            for call in tool_calls:
                if not isinstance(call, dict):
                    continue
                function = call.get("function")
                if not isinstance(function, dict):
                    continue
                name = str(function.get("name") or "?")
                arguments = function.get("arguments")
                if isinstance(arguments, str):
                    with contextlib.suppress(json.JSONDecodeError):
                        arguments = json.loads(arguments)
                if isinstance(arguments, dict):
                    params = ", ".join(f"{k}={_AgentCore._short_json(v, 160)}" for k, v in arguments.items())
                else:
                    params = _AgentCore._short_json(arguments)
                lines.append(f"      - {name}({params})")

        web_search = assistant_msg.get("web_search_call")
        if isinstance(web_search, list) and web_search:
            lines.append("  - web_search:")
            for item in web_search:
                if not isinstance(item, dict):
                    continue
                lines.append(f"      - id: {item.get('id')}")
                lines.append(f"        action: {_AgentCore._short_json(item.get('action'))}")

        return "\n".join(lines)

    def _tools_for_responses(self) -> list[dict[str, Any]] | None:
        """Responses API 工具格式(与 chat 的 function 包装不同)+ 服务端 web_search。"""
        tools: list[dict[str, Any]] = []
        for t in self.tools:
            fn = t["function"]
            tools.append(
                {
                    "type": "function",
                    "name": fn["name"],
                    "description": fn["description"],
                    "parameters": fn["parameters"],
                }
            )
        if self.web_search:
            tools.append({"type": "web_search"})
        return tools or None

    def _parse_output(self, resp: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        """解析 LLM 响应为 (动作列表, assistant 内部消息)。"""
        if self.api_mode == "responses":
            actions: list[dict[str, Any]] = []
            contents: list[str] = []
            tool_calls: list[dict[str, Any]] = []
            reasoning: list[dict[str, Any]] = []
            web_search: list[dict[str, Any]] = []
            order: list[str] = []  # 原始 item 顺序:回传时必须保持,DeepSeek 按此归并 assistant 轮次
            for item in resp.output:
                itype = getattr(item, "type", "")
                if itype == "message":
                    content = getattr(item, "content", "")
                    if isinstance(content, str):
                        contents.append(content)
                    else:
                        for part in content or []:
                            contents.append(getattr(part, "text", "") or "")
                    order.append("message")
                elif itype == "reasoning":
                    # 思考模式:reasoning item 必须完整回传,否则 API 400
                    reasoning.append(item.model_dump() if hasattr(item, "model_dump") else dict(item))
                    order.append("reasoning")
                elif itype == "function_call":
                    call_id = getattr(item, "call_id", "")
                    name = getattr(item, "name", "")
                    arguments = getattr(item, "arguments", "{}")
                    tool_calls.append(
                        {"id": call_id, "type": "function", "function": {"name": name, "arguments": arguments}}
                    )
                    actions.append({"kind": "function", "call_id": call_id, "name": name, "arguments": arguments})
                    order.append("function_call")
                elif itype == "web_search_call":
                    # 服务端搜索调用:必须完整回传(含 action/status),只回 id 会 400
                    web_search.append(item.model_dump() if hasattr(item, "model_dump") else dict(item))
                    order.append("web_search_call")
            raw_content = "".join(contents)
            if raw_content:
                # Flash 偶发把 DSML/XML 伪工具调用写进 content;解析为标准 function_call
                # 并清掉原文,避免污染 history 与后续请求。
                content, embedded_calls, embedded_actions = _parse_embedded_tool_calls(raw_content)
                if embedded_calls:
                    tool_calls.extend(embedded_calls)
                    actions.extend(embedded_actions)
                    # 回传顺序:message 之后补 function_call,工具执行后才有 output。
                    order.extend(["function_call"] * len(embedded_calls))
            else:
                content = raw_content
            assistant_msg: dict[str, Any] = {"role": "assistant", "content": content}
            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls
            if reasoning:
                assistant_msg["reasoning"] = reasoning
            if web_search:
                assistant_msg["web_search_call"] = web_search
                actions.append({"kind": "web_search", "data": web_search})
            if order:
                assistant_msg["order"] = order
            return actions, assistant_msg
        mess = resp.choices[0].message
        actions = [
            {
                "kind": "function",
                "call_id": tc.id,
                "name": cast(str, cast(Any, tc).function.name),
                "arguments": cast(str, cast(Any, tc).function.arguments),
            }
            for tc in (mess.tool_calls or [])
        ]
        assistant_msg: dict[str, Any] = mess.to_dict()
        raw_content = cast(str, getattr(mess, "content", "") or "")
        reasoning_content = getattr(mess, "reasoning_content", None)
        if reasoning_content:
            assistant_msg["reasoning"] = [
                {
                    "type": "reasoning",
                    "id": f"chat_reasoning_{int(time.time() * 1000)}",
                    "summary": list[str](),
                    "status": "completed",
                    "content": [{"type": "reasoning_text", "text": str(reasoning_content)}],
                }
            ]
        if raw_content:
            content, embedded_calls, embedded_actions = _parse_embedded_tool_calls(raw_content)
            assistant_msg["content"] = content
            if embedded_calls:
                assistant_msg["tool_calls"] = list(assistant_msg.get("tool_calls") or []) + embedded_calls
                actions.extend(embedded_actions)
        else:
            assistant_msg["content"] = ""
        return actions, assistant_msg


# --------------------------------------------------------------------------- #
# 消息收集器(移植自 HyperAG core/collecter.py,去掉 LLM checker)
# 差异:任何消息都先入缓存;只有白名单用户(或主人)发言才启动收集周期
# --------------------------------------------------------------------------- #


class _Collector:
    # 缓存窗口上限:达到后立刻压缩为单条摘要,再继续缓存
    MAX_BUFFER = 80

    def __init__(self, sid: int, stype: Literal["grp", "usr"], core: "_AgentCore") -> None:
        self.sid = sid
        self.stype = stype
        self.core = core
        self.buffer: list[dict[str, Any]] = []
        self.delay = 8.0
        self.doing_task: asyncio.Task[Any] | None = None
        self.last_receive = 0.0
        self.active = False
        self.replying = False
        self.principal_id: int | None = None
        self.perm_group = "member"
        self.self_id: int | None = None

    @staticmethod
    def _event_text(ev: dict[str, Any]) -> str:
        """从事件数据提取纯文本(非文本段以占位符表示)。"""
        parts: list[str] = []
        for seg in ev.get("message", []):
            if seg.get("type") == "text":
                parts.append((seg.get("data") or {}).get("text", ""))
            else:
                parts.append(f"[{seg.get('type')}]")
        return "".join(parts)

    def _timeline(self) -> str:
        """把 buffer 整理为紧凑时间线文本(发送者+时间+文本)。"""
        lines: list[str] = []
        for ev in self.buffer:
            uid = ev.get("user_id")
            t = ev.get("time")
            lines.append(f"[{t}] {uid}: {self._event_text(ev)}")
        return "\n".join(lines)

    async def _compress(self) -> dict[str, Any]:
        """把当前 buffer 压缩为单条摘要。

        优先用 Gemini Flash Lite 生成语义摘要(保留关键话题/事件/人物);
        失败或未配置时退回紧凑时间线拼接。
        """
        raw = self._timeline()
        try:
            key = config.others.get("gemini_key")
            if key:
                from google import genai

                cli = genai.Client(api_key=key)
                res = await asyncio.to_thread(
                    cli.models.generate_content,
                    model=GEMINI_MODEL,
                    contents="请将以下QQ群聊天记录压缩为一段简洁的中文摘要，保留关键话题、事件、人物与待办信息，不要寒暄：\n\n"
                    + raw[:8000],
                )
                summary = (res.text or "").strip()
                if summary:
                    return {
                        "compressed": True,
                        "note": f"以下为 {len(self.buffer)} 条消息的 LLM 摘要:",
                        "summary": summary,
                    }
        except Exception:
            logger.warning(f"{self.stype} {self.sid}: LLM 摘要失败,退回时间线拼接")
        return {
            "compressed": True,
            "note": f"以下为 {len(self.buffer)} 条消息的压缩摘要(按时间顺序,发送者+时间+文本):",
            "summary": raw,
        }

    async def _maybe_compress(self) -> None:
        """缓存达到窗口上限时,立即压缩为单条摘要后继续缓存。"""
        if len(self.buffer) >= self.MAX_BUFFER:
            self.buffer = [await self._compress()]
            logger.info(f"{self.stype} {self.sid}: 缓存达 {self.MAX_BUFFER} 条,已压缩为单条摘要")

    def _update_delay(self, last: float, length: int) -> None:
        rate = last / self.delay
        weight = 1 if length * 0.2 <= 1 else length * 0.2
        self.delay = (2 / 3) * (1 - math.cos(math.pi * rate)) + (2 / 3) * weight + 2.5
        self.delay = max(min(self.delay, 16), 5)

    async def append(self, event: MessageEvent) -> None:
        """向当前已启动的收集批次追加一条消息。"""
        await self.append_batch([event.data])

    async def append_batch(self, events: list[dict[str, Any]]) -> None:
        """把独立缓存的一批消息交给 Collector,并重置已启动窗口。"""
        if not events:
            return
        self.buffer.extend(events)
        await self._maybe_compress()
        now = time.time()
        length = len(str(events[-1].get("message", "")))
        if len(self.buffer) > len(events):
            self._update_delay(now - self.last_receive, length)
        else:
            weight = 1 if length * 0.2 <= 1 else length * 0.2
            self.delay = max(min(self.delay * weight, 16), 5)
        self.last_receive = now
        if self.active and not self.replying:
            if self.doing_task is not None and not self.doing_task.done():
                self.doing_task.cancel()
            self.doing_task = asyncio.create_task(self._sleep_loop())

    async def start(self, principal_id: int | None, perm_group: str, self_id: int | None = None) -> None:
        """开始(或确认已在进行中的)收集周期。"""
        if self.active or self.replying:
            return
        self.active = True
        self.principal_id = principal_id
        self.perm_group = perm_group
        self.self_id = self_id
        if self.doing_task is not None and not self.doing_task.done():
            self.doing_task.cancel()
        self.doing_task = asyncio.create_task(self._sleep_loop())

    async def _sleep_loop(self) -> None:
        try:
            await asyncio.sleep(self.delay)
            self.replying = True
            # 快照本次要处理的消息;处理期间新到的消息只追加进 buffer,不打断本轮
            batch = list(self.buffer)
            try:
                await self.core.event_handler(
                    event=json.dumps(batch, ensure_ascii=False),
                    ev_type="group" if self.stype == "grp" else "private",
                    scene_id=self.sid,
                    perm_group=self.perm_group,
                    principal_id=self.principal_id,
                    self_id=self.self_id,
                )
            except Exception:
                logger.error(traceback.format_exc())
            finally:
                self.replying = False
                # 只移除已处理的消息,保留处理期间新到的消息(按对象 id 过滤,
                # 避免处理期间 _maybe_compress 把 buffer 替换为摘要时误删)
                batch_ids = {id(x) for x in batch}
                self.buffer = [x for x in self.buffer if id(x) not in batch_ids]
                if self.buffer:
                    # 处理期间有新消息:立即进入新一轮收集
                    self.active = True
                    self.doing_task = asyncio.create_task(self._sleep_loop())
                else:
                    self.active = False
        except asyncio.CancelledError:
            pass


# --------------------------------------------------------------------------- #
# 模块调用:拦截模块发送、捕获为段 JSON 移交 Agent(其余 actions 透传真实执行)
# --------------------------------------------------------------------------- #


class _CaptureActions:
    """包装真实 Actions:send_* 被拦截收集,其余方法透传。

    模块通过 self.actions 发送的消息不会真正发出去,而是以 OneBot 段数组
    (message.get_sync())形式收集,供 Agent 决定如何转发/整合。
    图片段若指向本地 file:// 文件,会先复制到 ./temps/agent_capture/(模块常在
    send 后自行 os.remove 临时文件,不复制则 Agent 转发时文件已不存在)。
    """

    CAPTURE_DIR = "./temps/agent_capture"

    def __init__(self, real: Actions) -> None:
        self._real = real
        self.captured: list[dict[str, Any]] = []

    @staticmethod
    def _preserve_image_files(segs: list[Any]) -> list[Any]:
        """把本地 file:// 图片复制到持久目录,返回段副本(不改原段)。"""
        out: list[Any] = []
        for seg in segs:
            if isinstance(seg, dict) and seg.get("type") == "image":
                data = seg.get("data") or {}
                file = data.get("file", "")
                if file.startswith("file://"):
                    src = file[len("file://") :]
                    if os.path.isfile(src):
                        try:
                            os.makedirs(_CaptureActions.CAPTURE_DIR, exist_ok=True)
                            dst = os.path.join(
                                _CaptureActions.CAPTURE_DIR,
                                f"{int(time.time() * 1000)}_{os.path.basename(src)}",
                            )
                            import shutil

                            shutil.copy2(src, dst)
                            file = "file://" + os.path.abspath(dst).replace("\\", "/")
                        except OSError:
                            pass
                    seg = dict(seg)
                    seg["data"] = dict(data)
                    seg["data"]["file"] = file
            out.append(seg)
        return out

    async def send_msg(
        self,
        group_id: int | None = None,
        user_id: int | None = None,
        message: Any = None,
        **kw: Any,
    ) -> dict[str, Any]:
        segs: list[Any] = []
        try:
            segs = message.get_sync() if message is not None else []
        except Exception:
            segs = [{"type": "text", "data": {"text": str(message)}}]
        segs = self._preserve_image_files(segs)
        self.captured.append({"group_id": group_id, "user_id": user_id, "message": segs})
        # 伪装成功返回,避免模块因返回结构不符而异常
        return {"status": "ok", "retcode": 0, "data": {"message_id": 0}}

    async def send_group_msg(self, group_id: int | None, message: Any, **kw: Any) -> dict[str, Any]:
        return await self.send_msg(group_id=group_id, message=message, **kw)

    async def send_private_msg(self, user_id: int | None, message: Any, **kw: Any) -> dict[str, Any]:
        return await self.send_msg(user_id=user_id, message=message, **kw)

    async def send_forward_msg(self, message: Any, **kw: Any) -> dict[str, Any]:
        return await self.send_msg(message=message, **kw)

    async def send_group_forward_msg(self, group_id: int | None, message: Any, **kw: Any) -> dict[str, Any]:
        return await self.send_msg(group_id=group_id, message=message, **kw)

    def __getattr__(self, name: str) -> Any:
        # 查询/操作类方法(如 get_version_info / set_group_ban)透传真实执行
        return getattr(self._real, name)


# --------------------------------------------------------------------------- #
# SubAgent(主 Agent 创建的后台分身:独立提示词 + 独立 core,共享工具注册表)
# --------------------------------------------------------------------------- #


class _SubAgent:
    def __init__(
        self,
        sub_id: int,
        name: str,
        prompt: str,
        scene_type: str,
        scene_id: int,
        perm_group: str,
        core: _AgentCore,
    ) -> None:
        self.sub_id = sub_id
        self.name = name
        self.prompt = prompt
        self.scene_type = scene_type  # 归属场景(仅标识;SubAgent 不监听 QQ 消息流)
        self.scene_id = scene_id
        self.perm_group = perm_group  # 创建者的权限档位(链式继承)
        self.core = core
        self.status = "running"
        self.created_at = int(time.time())


class _SubAgentManager:
    """SubAgent 生命周期管理:创建/销毁/列表/状态/投喂;数量上限 MAX_SUBAGENTS。"""

    MAX_SUBAGENTS = 3

    def __init__(self, owner: "_Agent") -> None:
        self.owner = owner
        self.subagents: dict[int, _SubAgent] = {}
        self._next_id = 1

    def _notify(self, payload: dict[str, Any]) -> None:
        """状态变化通知主 Agent:构造 subagent_status 事件注入主 Agent history。"""
        main_core = self.owner.core
        if main_core is None:
            return
        ev = AgentEvent(type="subagent_status", scene_type="system", scene_id=0, payload=payload, source="sub")
        main_core.inject_notice(ev)
        logger.info(f"SubAgent 状态通知主 Agent: {payload}")

    async def create(self, name: str, prompt: str, scene_type: str, scene_id: int, perm_group: str = "member") -> str:
        if len(self.subagents) >= self.MAX_SUBAGENTS:
            return f"SubAgent 数量已达上限({self.MAX_SUBAGENTS}),请先销毁其他 SubAgent 再创建"
        if scene_type not in ("group", "private"):
            return f"调用不合法：scene_type 必须为 group 或 private，当前为 {scene_type}"
        sub_id = self._next_id
        self._next_id += 1
        core = _AgentCore(
            bot_api=self.owner._core().bot_api,
            key=cast(str, config.others.get("openai_key")),
            model=cast(str, config.others.get("openai_model")),
            base_url=cast(str, config.others.get("openai_endpoint") or ""),
            system_prompt=prompt,
            name=f"sub:{sub_id}",
            history_path=f"./temps/agent_sub_{sub_id}_history.json",
            tasks_path=f"./temps/agent_sub_{sub_id}_tasks.json",
            memory_path=f"./temps/agent_sub_{sub_id}_memory",
            notify_main=self._notify,
        )
        sub = _SubAgent(sub_id, name, prompt, scene_type, scene_id, perm_group, core)
        self.subagents[sub_id] = sub
        self._notify(
            {
                "action": "created",
                "sub_id": sub_id,
                "name": name,
                "scene": f"{scene_type}:{scene_id}",
                "total": f"{len(self.subagents)}/{self.MAX_SUBAGENTS}",
            }
        )
        return f"SubAgent #{sub_id}「{name}」已创建并订阅 {scene_type}:{scene_id}(当前 {len(self.subagents)}/{self.MAX_SUBAGENTS})"

    async def destroy(self, sub_id: int) -> str:
        sub = self.subagents.pop(sub_id, None)
        if sub is None:
            return f"SubAgent #{sub_id} 不存在"
        for p in (
            sub.core.history_path,
            sub.core.tasks_path,
            sub.core.memory_path + ".json",
            sub.core.memory_path + ".npz",
        ):
            if os.path.exists(p):
                os.remove(p)
        self._notify(
            {
                "action": "destroyed",
                "sub_id": sub_id,
                "name": sub.name,
                "total": f"{len(self.subagents)}/{self.MAX_SUBAGENTS}",
            }
        )
        return f"SubAgent #{sub_id}「{sub.name}」已销毁(当前 {len(self.subagents)}/{self.MAX_SUBAGENTS})"

    def list(self) -> str:
        if not self.subagents:
            return f"暂无 SubAgent(0/{self.MAX_SUBAGENTS})"
        lines = [f"SubAgent 列表({len(self.subagents)}/{self.MAX_SUBAGENTS}):"]
        for sid, sub in self.subagents.items():
            lines.append(
                f"#{sid} 「{sub.name}」[{sub.status}] 订阅 {sub.scene_type}:{sub.scene_id} 创建于 {sub.created_at}"
            )
        return "\n".join(lines)

    def status(self, sub_id: int) -> str:
        sub = self.subagents.get(sub_id)
        if sub is None:
            return f"SubAgent #{sub_id} 不存在"
        return (
            f"SubAgent #{sub_id}「{sub.name}」\n"
            f"状态: {sub.status} | 订阅: {sub.scene_type}:{sub.scene_id} | 权限: {sub.perm_group}\n"
            f"创建于: {sub.created_at} | 历史消息数: {len(sub.core.history)}"
        )

    async def feed(self, sub_id: int, content: str, perm_group: str = "member") -> str:
        sub = self.subagents.get(sub_id)
        if sub is None:
            return f"SubAgent #{sub_id} 不存在"
        asyncio.create_task(
            sub.core.event_handler(
                event=content,
                ev_type=cast(Literal["group", "private"], sub.scene_type),
                scene_id=sub.scene_id,
                perm_group=perm_group,
            )
        )
        return f"已向 SubAgent #{sub_id}「{sub.name}」投喂消息"


# --------------------------------------------------------------------------- #
# Agent 门面(持有核心与各会话收集器)
# --------------------------------------------------------------------------- #


class _Agent:
    def __init__(self) -> None:
        self.core: _AgentCore | None = None
        self.collectors: dict[int, _Collector] = {}
        self.group_cache: dict[int, list[dict[str, Any]]] = {}
        self.sub_manager: _SubAgentManager | None = None
        self.heartbeat_task: asyncio.Task[Any] | None = None
        self.acted = 0

    # -- 白名单 --

    @staticmethod
    def _group_white(gid: int) -> set[int]:
        s = _white.get(gid)
        if s is None:
            s = set()
            _white[gid] = s
        return s

    @staticmethod
    def _save_white() -> None:
        # 直接读写 config.json 而非 config.write():
        # cfgr 的 dump() 只写声明字段且类型在 [str,int,float,list,dict] 白名单内的键,
        # bool 类型的 log_use_nf 会被静默丢弃(导致日志 NerdFont 图标丢失)
        with open("config.json", encoding="utf-8") as f:
            cfg = json.load(f)
        others = cfg.setdefault("others", {})
        others["agent_white"] = {str(k): sorted(v) for k, v in _white.items()}
        with open("config.json", "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)

    async def apply_profile(self, name: str) -> str:
        """命令侧人设切换:与 bot 工具 switch_profile 共用 _AgentCore.switch_profile(含切换前自动总结)。"""
        return await self._core().switch_profile(name)

    @staticmethod
    def add_profile(name: str, content: str) -> str:
        """新增/覆盖 profiles.json 中的人设条目(不自动切换)。

        旧版字符串条目升级为对象时默认 inject_master=True(保持原行为);
        覆盖已有对象条目时保留其 inject_master 选项。
        """
        if not name.strip() or not content.strip():
            return "人设名称与内容不能为空"
        profiles = _load_profiles()
        existed = name in profiles
        previous = profiles.get(name)
        inject_master = previous.inject_master if previous is not None else True
        profiles[name] = _AgentProfile(content.strip(), inject_master)
        try:
            _save_profiles(profiles)
        except OSError:
            return f"写入 {PROFILES_PATH} 失败(文件只读?)"
        logger.info(f"人设「{name}」已{'更新' if existed else '添加'}")
        return f"人设「{name}」已{'更新' if existed else '添加'},发送 .agent.profile {name} 可立即启用"

    @staticmethod
    def remove_profile(name: str) -> str:
        """删除 profiles.json 中的人设;不允许删除当前使用中的人设。"""
        profiles = _load_profiles()
        if name not in profiles:
            return f"人设「{name}」不存在,可用: {', '.join(profiles.keys()) or '(无)'}"
        if name == _current_profile_name():
            return f"人设「{name}」正在使用中,请先切换其他人设再删除"
        del profiles[name]
        try:
            _save_profiles(profiles)
        except OSError:
            return f"写入 {PROFILES_PATH} 失败(文件只读?)"
        logger.info(f"人设「{name}」已删除")
        return f"人设「{name}」已删除"

    async def set_profile_master(self, name: str, enabled: bool | None) -> str:
        """查看或设置指定人设的 inject_master;当前人设会热更新 system prompt。"""
        profiles = _load_profiles()
        profile = profiles.get(name)
        if profile is None:
            return f"人设「{name}」不存在,可用: {', '.join(profiles.keys()) or '(无)'}"
        if enabled is None:
            return f"人设「{name}」的 inject_master：{'开启' if profile.inject_master else '关闭'}"
        if profile.inject_master == enabled:
            return f"人设「{name}」的 inject_master 已经是{'开启' if enabled else '关闭'}状态"
        updated = _AgentProfile(profile.prompt, enabled)
        profiles[name] = updated
        try:
            _save_profiles(profiles)
        except OSError:
            return f"写入 {PROFILES_PATH} 失败(文件只读?)"
        if name == _current_profile_name():
            core = self._core()
            await core._acquire_processing_slot()
            try:
                core._apply_profile_prompt(updated)
                await core.save()
            finally:
                await core._release_processing_slot()
        logger.info(f"人设「{name}」的 inject_master 已设置为 {enabled}")
        return f"人设「{name}」的 inject_master 已{'开启' if enabled else '关闭'}"

    def _core(self) -> "_AgentCore":
        assert self.core is not None
        return self.core

    def _perm_of(self, uid: int | None, gid: int | None) -> str:
        """权限档位:配置主人 → bot_owner;群白名单 → whitelist;否则 member(私聊不设白名单)。"""
        if uid is None:
            return "member"
        if uid in config.owner:
            return "bot_owner"
        if gid is not None and uid in self._group_white(gid):
            return "whitelist"
        return "member"

    # -- 入口 --

    async def on_event(self, actions: Actions, event: MessageEvent) -> None:
        if self.core is None:
            self.core = _AgentCore(
                bot_api=actions,
                key=cast(str, config.others.get("openai_key")),
                model=cast(str, config.others.get("openai_model")),
                base_url=cast(str, config.others.get("openai_endpoint") or ""),
            )
            self.sub_manager = _SubAgentManager(self)
            self.core.sub_manager = self.sub_manager
            if config.others.get("agent_heartbeat") and self.heartbeat_task is None:
                self.heartbeat_task = asyncio.create_task(self._heartbeat())
        if isinstance(event, GroupMessageEvent):
            await self._on_group(event)
        elif isinstance(event, PrivateMessageEvent):
            await self._on_private(event)

    async def _on_group(self, event: GroupMessageEvent) -> None:
        if event.group_id is None or event.user_id is None or event.blocked or event.is_silent:
            return
        text = str(event.message).strip()
        if text.startswith((".agent", ".ag")):
            await self._cmd(event)
            return
        if event.is_mentioned:
            await self._immediate(event)
            return
        if not _white.get(event.group_id) and not event.is_owner:
            # 没有任何白名单设置的群:普通成员消息不缓存,主人仍可直接触发。
            return
        cache = self.group_cache.setdefault(event.group_id, [])
        cache.append(event.data)
        if event.user_id not in self._group_white(event.group_id) and not event.is_owner:
            # 普通成员只进入独立缓存,不启动/重置 Collector 收集窗口。
            return
        col = self.collectors.setdefault(event.group_id, _Collector(event.group_id, "grp", self._core()))
        await col.append_batch(cache)
        cache.clear()
        await col.start(event.user_id, self._perm_of(event.user_id, event.group_id), event.self_id)

    async def _on_private(self, event: PrivateMessageEvent) -> None:
        if event.user_id is None or event.blocked or event.is_silent:
            return
        text = str(event.message).strip()
        if text.startswith((".agent", ".ag")):
            await self._cmd(event)
            return
        uid = event.user_id
        if uid in config.owner:
            # 主人私聊:不走收集,立即处理
            asyncio.create_task(
                self._process([event.data], "private", uid, self._perm_of(uid, None), uid, event.self_id)
            )
            return
        # 私聊不配置白名单:所有消息都走收集处理
        col = self.collectors.setdefault(uid, _Collector(uid, "usr", self._core()))
        await col.append(event)
        await col.start(uid, self._perm_of(uid, None), event.self_id)

    # -- 立即处理(被 @ / 主人私聊) --

    async def _immediate(self, event: GroupMessageEvent) -> None:
        gid = cast(int, event.group_id)
        col = self.collectors.setdefault(gid, _Collector(gid, "grp", self._core()))
        cache = self.group_cache.pop(gid, [])
        batch = cache + list(col.buffer) + [event.data]
        col.buffer.clear()
        if col.doing_task is not None and not col.doing_task.done():
            col.doing_task.cancel()
        col.doing_task = None
        col.active = False
        asyncio.create_task(
            self._process(batch, "group", gid, self._perm_of(event.user_id, gid), event.user_id, event.self_id)
        )

    async def _process(
        self,
        batch: list[dict[str, Any]],
        ev_type: Literal["group", "private"],
        scene_id: int,
        perm_group: str,
        principal_id: int | None,
        self_id: int | None = None,
    ) -> None:
        try:
            await self._core().event_handler(
                event=json.dumps(batch, ensure_ascii=False),
                ev_type=ev_type,
                scene_id=scene_id,
                perm_group=perm_group,
                principal_id=principal_id,
                self_id=self_id,
            )
            self.acted += 1
        except Exception:
            logger.error(traceback.format_exc())

    # -- 命令 --

    async def _cmd(self, event: MessageEvent) -> None:
        uid = cast(int, event.user_id)
        gid = event.group_id
        text = str(event.message).strip()
        # 归一化:兼容 ".agent.on" 与 ".agent on";简写 ".ag" 等价 ".agent"(如 ".ag.pf.ad")
        if text.startswith(".agent.") or text.startswith(".ag."):
            prefix = ".agent." if text.startswith(".agent.") else ".ag."
            text = ".agent " + text[len(prefix) :]
        parts = text.split()
        sub = parts[1] if len(parts) > 1 else ""
        # 子命令简写 → 全拼:profile/pf, context/ctx, add/ad, remove/rm, summary/sum, clear/clr
        sub = {
            "pf": "profile",
            "ctx": "context",
            "pf.ad": "profile.add",
            "pf.rm": "profile.remove",
            "pf.list": "profile.list",
            "pf.master": "profile.master",
            "pf.ma": "profile.master",
            "profile.ma": "profile.master",
            "ctx.clr": "context.clear",
            "ctx.sum": "context.summary",
            "function": "func",
            "func.enable": "func.en",
            "function.en": "func.en",
            "function.enable": "func.en",
            "func.disable": "func.dis",
            "function.dis": "func.dis",
            "function.disable": "func.dis",
        }.get(sub, sub)
        if sub == "on":
            if gid is not None:
                self._group_white(gid).add(uid)
                self._save_white()
                msg = "已开启本群内 Agent 对您的消息的自动处理"
            else:
                msg = "私聊自动处理始终开启,无需白名单"
            await self._reply(event, msg)
        elif sub == "off":
            if gid is not None:
                self._group_white(gid).discard(uid)
                self._save_white()
                msg = "已关闭本群内 Agent 对您的消息的自动处理"
            else:
                msg = "私聊自动处理始终开启,无需白名单"
            await self._reply(event, msg)
        elif sub == "status":
            if gid is not None:
                enabled = uid in self._group_white(gid) or event.is_owner
                total = len(self._group_white(gid))
                msg = f"本群 Agent 自动处理：{'开启' if enabled else '关闭'}（白名单共 {total} 人，主人始终开启）"
            else:
                msg = "私聊 Agent 自动处理：开启（无需白名单）"
            await self._reply(event, msg)
        elif sub == "profile.add":
            if len(parts) < 4:
                await self._reply(event, "用法: .agent.profile.add <名称> <人设内容(可含空格)>")
                return
            if uid not in config.owner:
                await self._reply(event, "仅主人可添加人设")
                return
            # split(None, 3):只切前 3 段,name 之后的内容原样保留(含内部连续空格)
            _, _, name, content = text.split(None, 3)
            await self._reply(event, self.add_profile(name, content))
        elif sub == "profile.master":
            target = parts[2] if len(parts) > 2 else ""
            if target == "":
                await self._reply(event, "用法: .agent.profile.master <名称> [on/off]")
                return
            value = parts[3] if len(parts) > 3 else ""
            if value == "":
                enabled: bool | None = None
            else:
                if uid not in config.owner:
                    await self._reply(event, "仅主人可设置 inject_master")
                    return
                value_l = value.lower()
                if value_l in ("on", "true", "1", "开", "开启"):
                    enabled = True
                elif value_l in ("off", "false", "0", "关", "关闭"):
                    enabled = False
                else:
                    await self._reply(event, "用法: .agent.profile.master <名称> [on/off]")
                    return
            await self._reply(event, await self.set_profile_master(target, enabled))
        elif sub == "profile.remove":
            target = parts[2] if len(parts) > 2 else ""
            if target == "":
                await self._reply(event, "用法: .agent.profile.remove <名称>")
                return
            if uid not in config.owner:
                await self._reply(event, "仅主人可删除人设")
                return
            await self._reply(event, self.remove_profile(target))
        elif sub in ("profile", "profile.list"):
            target = parts[2] if len(parts) > 2 else ""
            if target == "" or sub == "profile.list":
                profiles = _load_profiles()
                cur = _current_profile_name()
                listing = ", ".join(f"{n}{'(当前)' if n == cur else ''}" for n in profiles)
                await self._reply(event, f"可用人设: {listing}\n当前: {cur}")
                return
            if uid not in config.owner:
                await self._reply(event, "仅主人可切换人设")
                return
            await self._reply(event, await self.apply_profile(target))
        elif sub == "context":
            if uid not in config.owner:
                await self._reply(event, "仅主人可管理上下文")
                return
            await self._reply(event, self._core().context_info())
        elif sub == "context.clear":
            if uid not in config.owner:
                await self._reply(event, "仅主人可管理上下文")
                return
            await self._reply(event, await self._core().reset_history())
        elif sub == "context.summary":
            if uid not in config.owner:
                await self._reply(event, "仅主人可管理上下文")
                return
            await self._reply(event, await self._core().summarize_current_context())
        elif sub == "func":
            if uid not in config.owner:
                await self._reply(event, "仅主人可管理 Agent 工具")
                return
            await self._reply(event, _func_status_text())
        elif sub == "func.en":
            name = parts[2] if len(parts) > 2 else ""
            if name == "":
                await self._reply(event, "用法: .ag.func.en <name>")
                return
            if uid not in config.owner:
                await self._reply(event, "仅主人可管理 Agent 工具")
                return
            await self._reply(event, ToolRegistry.enable_tool(name))
        elif sub == "func.dis":
            name = parts[2] if len(parts) > 2 else ""
            if name == "":
                await self._reply(
                    event,
                    "用法: .ag.func.dis <name> <duration?>\n"
                    "时长支持 30s/5m/1h/1d 或 30秒/5分钟/1小时/1天,裸数字为分钟;"
                    "不填=禁用至手动启用",
                )
                return
            if uid not in config.owner:
                await self._reply(event, "仅主人可管理 Agent 工具")
                return
            if len(parts) > 3:
                try:
                    minutes = _parse_duration_minutes(parts[3])
                except ValueError:
                    await self._reply(
                        event,
                        "时长格式错误:支持 30s/5m/1h/1d 或 30秒/5分钟/1小时/1天,裸数字为分钟",
                    )
                    return
                duration_text = parts[3]
            else:
                minutes = None
                duration_text = ""
            await self._reply(event, ToolRegistry.disable_tool(name, minutes, duration_text))
        else:
            # 帮助信息由 Helps 模块统一展示(.help Agent),不在本模块内自回复
            await self._reply(event, "未知的子命令。发送 .help Agent 查看模块帮助")

    async def _reply(self, event: MessageEvent, text: str) -> None:
        await self._core().bot_api.send_msg(
            group_id=event.group_id,
            user_id=event.user_id,
            message=common.Message(segments.Reply(event.message_id), segments.Text(text)),
        )

    # -- 心跳(可选,默认关闭) --

    async def _heartbeat(self) -> None:
        base_time = 5.0
        while True:
            last_acted = self.acted
            await asyncio.sleep(60 * base_time)
            if base_time >= 2:
                await self._core().event_handler(
                    event=f"Heartbeat {base_time} mins",
                    ev_type="system",
                    scene_id=0,
                    perm_group="bot_owner",
                    principal_id=None,
                )
            delta = self.acted - last_acted
            if delta == 0:
                base_time = base_time * 4
            elif 0 < delta / base_time <= 0.7:
                base_time = base_time * 2
            elif 0.7 < delta / base_time <= 1:
                base_time = base_time * 1
            elif 1 < delta / base_time <= 1.2:
                base_time = base_time * 0.5
            elif 1.2 < delta / base_time <= 2:
                base_time = base_time * 0.25
            else:
                base_time = base_time * 0.12
            if base_time < 2:
                base_time = 2


_agent = _Agent()


@ModuleClass.ModuleRegister.register(GroupMessageEvent, PrivateMessageEvent)
class Module(ModuleClass.Module[GroupMessageEvent | PrivateMessageEvent]):
    @override
    @staticmethod
    def info() -> ModuleClass.ModuleInfo:
        return ModuleClass.ModuleInfo(
            is_hidden=False,
            module_name="Agent",
            desc="自主 Agent(移植自 HyperAG)",
            helps=AGENT_HELP,
        )

    @override
    async def handle(self) -> None:
        await _agent.on_event(self.actions, self.event)
