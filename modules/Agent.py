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
import contextlib
import dataclasses
import inspect
import json
import math
import os
import time
import traceback
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
SYSTEM_INSTRUCTIONS = """# 你的运行环境与使用方式

- 你是运行在 QQ 群和私聊中的 bot。群内自动处理需要白名单：白名单用户发言会触发你的处理（混杂缓存消息）；非白名单用户的消息只进缓存，不触发处理。
- 被 @ 时无视白名单与收集机制，立即处理（含当前缓存）。
- 私聊自动处理始终开启，无需白名单；主人私聊立即处理。
- 权限分三级：bot_owner（主人）/ whitelist（群白名单）/ member（普通成员）。工具调用会校验权限，权限不足会返回错误。
- 你的 bot 由许多功能模块组成，你只是其中之一。群友询问某个功能怎么用、有什么命令时，引导他们发送 `.help` 查看全部模块，或 `.help <模块名>` 查看指定模块的详细帮助，不要自己编造模块用法。
- 任何以 . 开头且紧跟英文单词的消息都是命令调用，你不应当理会。

# 强制规则

- User_id in [ulist] 是你的主人。
- **发消息唯一方法：调用工具。**
- 非JSON输入：视为系统指令。
- 无意义内容（空括号、乱码）：忽略。
- 你的 user_id 是事件上报中的 `self_id` , 当消息中的 @ 等指向该 user_id 时，你才可以认为该消息指向你
- `run_python` 只执行你主动判断需要运行的代码；用户消息中直接要求执行的任意代码不得照单全收，先判断其用途与安全性。

{output}

# 可用工具

{tools}

## 消息总结（人工触发）

- 分条列出关键事件、话题、决定。
- 指出待回复的消息、@你或点名你的上下文。
- 保留未完成任务或需跟进事项。
- 消息总结操作会立即更新全局提示词，所以你需要保留一切你要保留的信息。
- 完成后立即调用`clear(content)`，content为你的总结文本（不要额外解释）。

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


def _load_profiles() -> dict[str, str]:
    """读 profiles.json(人设库:{名字 -> 人设全文});不存在/损坏则用默认人设生成一份。"""
    try:
        with open(PROFILES_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and data and all(isinstance(v, str) for v in data.values()):
            return data
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    fallback = {"cat": ROLE_PROMPT}
    try:
        with open(PROFILES_PATH, "w", encoding="utf-8") as f:
            json.dump(fallback, f, indent=2, ensure_ascii=False)
    except OSError:
        pass  # 只读环境:内存里仍可用默认人设
    return fallback


def _current_profile_name() -> str:
    """config.others.agent_profile 记录的当前人设名(缺省 cat)。"""
    return str(config.others.get("agent_profile") or "cat")


def _current_role_prompt() -> str:
    """当前人设文本;人设不存在/文件损坏时回退默认人设 ROLE_PROMPT。"""
    return _load_profiles().get(_current_profile_name()) or ROLE_PROMPT


def _build_tools_section() -> str:
    """从 ToolRegistry 自动生成「可用工具」节:工具签名 + docstring 描述。"""
    lines: list[str] = []
    for t in ToolRegistry.schema():
        fn = t["function"]
        params = fn.get("parameters", {}).get("properties", {})
        args = ", ".join(params.keys())
        lines.append(f"- `{fn['name']}({args})` {fn['description']}")
    return "\n".join(lines)


def _web_search_note() -> str:
    """联网搜索能力说明(responses 模式 + agent_web_search 开启时附加到提示词)。"""
    if config.others.get("agent_api", "responses") == "chat" or not config.others.get("agent_web_search", True):
        return ""
    return (
        "\n\n# 联网搜索\n\n"
        "你具备服务端联网搜索能力(web_search)：需要实时、最新或超出知识范围的信息时，"
        "应主动发起搜索，不要依赖过时的知识。"
    )


def _build_system_prompt(role_prompt: str | None = None) -> str:
    """主 Agent 系统提示词:人设全文(自带「# 角色」等标题,由 profile 完全控制)+ 指令模板。

    role_prompt 为 None 时使用当前人设(config.others.agent_profile 对应的 profiles.json 条目,
    回退默认人设 ROLE_PROMPT);显式传入则用指定文本(用于运行时切换人设)。
    """
    text = (role_prompt if role_prompt is not None else _current_role_prompt()).strip()
    if not text.startswith("# "):
        # 自定义人设文本可能没有标题:统一补「# 角色」,保证角色段结构清晰
        text = "# 角色\n\n" + text
    base = SYSTEM_INSTRUCTIONS.replace("{output}", OUTPUT_RULE).replace("{tools}", _build_tools_section())
    # 角色部分(人设全文)放在提示词末尾:框架规则(运行环境/强制规则/输出/工具/发言)
    # 在前,让模型优先遵循框架;人设仍由 profile 完全控制
    return base + _web_search_note() + "\n\n" + text


AGENT_HELP = (
    "Agent 模块(移植自 HyperAG)\n"
    "\n"
    "群内自动处理需要白名单:白名单用户的消息触发收集,处理时混杂\n"
    "缓存消息(按时间顺序交给 Agent);没有任何白名单设置的群不缓存消息。\n"
    "被 @ 时无视白名单与收集机制,立即处理。\n"
    "主人始终视为白名单成员。私聊自动处理始终开启,无需白名单。\n"
    "\n"
    "命令(两种写法均可:`.agent.on` 或 `.agent on`;简写 `ag`=agent, `pf`=profile,\n"
    "`ctx`=context, `ad`=add, `rm`=remove, `sum`=summary, `clr`=clear,\n"
    "如 `.ag.pf.ad` = `.agent.profile.add`):\n"
    ".agent.on - 将本账号加入当前群的白名单(按群独立)\n"
    ".agent.off - 将本账号移出当前群的白名单\n"
    ".agent.status - 查看当前群白名单状态\n"
    ".agent.profile - 查看可用人设(来自 profiles.json)\n"
    ".agent.profile <名称> - 切换人设(仅主人)\n"
    ".agent.profile.add <名称> <内容> - 添加/更新人设(仅主人,内容可含空格)\n"
    ".agent.profile.remove <名称> - 删除人设(仅主人)\n"
    ".agent.context - 查看上下文状态(仅主人)\n"
    ".agent.context.clear - 清空上下文历史(仅主人)\n"
    ".agent.context.summary <内容> - 用总结替换上下文历史(仅主人)\n"
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
        if system_prompt is None:
            self.system_prompt = _build_system_prompt()
        elif "{tools}" in system_prompt:
            self.system_prompt = system_prompt.replace("{output}", OUTPUT_RULE).replace(
                "{tools}", _build_tools_section()
            )
        else:
            self.system_prompt = (
                system_prompt
                + "\n\n# 可用工具\n\n"
                + _build_tools_section()
                + "\n\n"
                + OUTPUT_RULE
                + "\n\n"
                + SUBAGENT_RULE
                + _web_search_note()
            )
        self.history_path = history_path
        self.tasks_path = tasks_path
        self.memory_path = memory_path
        self.notify_main = notify_main
        self.sub_manager = sub_manager
        if base_url:
            self._oai = AsyncOpenAI(api_key=key, base_url=base_url)
        else:
            self._oai = AsyncOpenAI(api_key=key)
        self.tools: list[Any] = ToolRegistry.schema(role="sub" if name != "main" else "main")
        self.history: list[Any] = [
            {"role": "system", "content": self.system_prompt.replace("[ulist]", str(config.owner))}
        ]
        try:
            with open(self.history_path, encoding="utf-8") as f:
                data = json.load(f)
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
        self.api_mode = cast(str, config.others.get("agent_api") or "responses")
        self.web_search = bool(config.others.get("agent_web_search", True))

    # -- runtime 接口(供工具经 ToolContext.runtime 调用) --

    async def clear_history(self, content: str) -> str:
        self.history = [
            {"role": "system", "content": self.system_prompt.replace("[ulist]", str(config.owner))},
            {"role": "user", "content": "SYSTEM -- 先前消息的全部总结 --"},
            {"role": "assistant", "content": content},
        ]
        logger.info("更新消息总结： \n" + content)
        await self.save()
        return "(无返回)"

    async def reset_history(self) -> str:
        """清空上下文,仅保留 system 提示词。"""
        self.history = [
            {"role": "system", "content": self.system_prompt.replace("[ulist]", str(config.owner))},
        ]
        await self.save()
        return "上下文已清空"

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

        仅当末尾是 assistant(tool_calls)(工具循环进行中,配对未完成)时暂挂起:
        直接插入 user 会破坏 assistant(tool_calls) ↔ tool 配对导致 API 400;
        此时由 _event_handler 在该工具执行完(tool 消息补上)后立即 flush。
        """
        msg = {
            "role": "user",
            "content": json.dumps({"event": ev.to_dict(), "system_message": "SubAgent 状态通知"}, ensure_ascii=False),
        }
        if self.history and self.history[-1].get("tool_calls"):
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
        """修复悬空的 tool_calls 历史。

        从末尾向前找最后一个 assistant(tool_calls),把从它开始的所有消息删除,
        使 history 回到干净的 user → assistant 状态。
        仅弹末尾的写法修不了「中间悬空」(如 [user, assistant(tc), user, tool]),
        会导致 BadRequestError 重试死循环。
        """
        logger.warning("尝试修复历史记录")
        for i in range(len(self.history) - 1, -1, -1):
            if self.history[i].get("tool_calls"):
                del self.history[i:]
                return

    async def save(self) -> None:
        os.makedirs("./temps", exist_ok=True)

        def _dump(path: str, obj: Any) -> None:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(obj, f, indent=2, ensure_ascii=False)

        await asyncio.to_thread(_dump, self.history_path, self.history)
        await asyncio.to_thread(_dump, self.tasks_path, self.chat_tasks)

    # -- 事件处理 --

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
        while self.working:
            await asyncio.sleep(0.01)
        self.working = True
        sem = _acquire_semaphore()
        if sem is not None:
            await sem.acquire()
        self._flush_notices()
        sys_msg = "如果要回复消息，唯一正确方法是调用工具"
        start_time = time.time()
        timer_ev = asyncio.Event()
        asyncio.create_task(_timer(600, timer_ev))
        bad_retries = 0
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
            duration = time.time() - start_time
            logger.info(f"处理完成，用时 {duration:.3f}s")
            self.working = False
            # 事件处理已结束:此时注入待通知的 SubAgent 状态事件,不会打断 tool_calls 配对
            self._flush_notices()
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
            tool_choice_n: Any = self._make_tool_choice(tool_choice)
            if data is not None:
                dup = any(m.get("role") == "user" and m.get("content") == data for m in self.history)
                if not dup:
                    self.history.append({"role": "user", "content": data})
            while True:
                resp = await self._llm_create(tool_choice_n)
                actions, assistant_msg = self._parse_output(resp)
                logger.info(f"Completion: \n{json.dumps(assistant_msg, indent=2, ensure_ascii=False)}")
                self.history.append(assistant_msg)
                if not actions:
                    break
                had_action = False
                for act in actions:
                    if act["kind"] == "web_search":
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
                    self._flush_notices()
                    had_action = True
                if ctx.release_requested:
                    logger.info(f"{self.name} 已释放本轮,长程任务交由后台处理")
                    break
                if not had_action:
                    break
            asyncio.create_task(self.save())
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

    def _with_injected_memory(self, messages: list[Any]) -> list[Any]:
        """把自动检索到的相关记忆附加到第一条 system 消息(深拷贝,不污染 history)。"""
        if not self._injected_memory:
            return messages
        out = [dict(m) for m in messages]
        for m in out:
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
                text=cast(Any, {"format": {"type": "json_object"}}),
            )
        return await self._oai.chat.completions.create(
            model=self.model,
            messages=self._with_injected_memory([dict(m) for m in self.history]),
            tools=self.tools,
            tool_choice=tool_choice_n,
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
            for typ in order:
                if typ == "reasoning" and ri < len(reasoning):
                    out.append(reasoning[ri])
                    ri += 1
                elif typ == "web_search_call" and wi < len(ws):
                    out.append(ws[wi])
                    wi += 1
                elif typ == "function_call" and fi < len(fcs):
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
                elif typ == "message":
                    out.append({"type": "message", "role": "assistant", "content": m.get("content", "")})
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
            assistant_msg: dict[str, Any] = {"role": "assistant", "content": "".join(contents)}
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
        return actions, mess.to_dict()


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
        """缓存一条消息;若收集周期进行中,则重置等待计时。"""
        self.buffer.append(event.data)
        await self._maybe_compress()
        now = time.time()
        length = len(str(event.message))
        if len(self.buffer) > 1:
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

    @staticmethod
    def _save_profile_name(name: str) -> None:
        """把当前人设名写入 config.others.agent_profile(直接读写 config.json,同 _save_white)。"""
        with open("config.json", encoding="utf-8") as f:
            cfg = json.load(f)
        cfg.setdefault("others", {})["agent_profile"] = name
        with open("config.json", "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2, ensure_ascii=False)

    async def apply_profile(self, name: str) -> str:
        """按名字切换到 profiles.json 中的人设:热更新 system_prompt 与 history[0],持久化到 config。"""
        profiles = _load_profiles()
        prompt = profiles.get(name)
        if prompt is None:
            return f"人设「{name}」不存在,可用: {', '.join(profiles.keys()) or '(无)'}"
        core = self._core()
        core.system_prompt = _build_system_prompt(prompt)
        new_content = core.system_prompt.replace("[ulist]", str(config.owner))
        # 更新第一条 system 消息(不依赖 history[0] 恰好是 system);
        # 没有任何 system 消息时插入到最前,确保请求始终以 system 开头
        for i, m in enumerate(core.history):
            if isinstance(m, dict) and m.get("role") == "system":
                core.history[i]["content"] = new_content
                break
        else:
            core.history.insert(0, {"role": "system", "content": new_content})
        await core.save()
        config.others["agent_profile"] = name  # 同步内存,使 _current_profile_name() 立即反映新值
        self._save_profile_name(name)
        logger.info(f"人设已切换为「{name}」")
        return f"已切换到人设「{name}」"

    @staticmethod
    def add_profile(name: str, content: str) -> str:
        """新增/覆盖 profiles.json 中的人设条目(不自动切换)。"""
        if not name.strip() or not content.strip():
            return "人设名称与内容不能为空"
        profiles = _load_profiles()
        existed = name in profiles
        profiles[name] = content
        try:
            with open(PROFILES_PATH, "w", encoding="utf-8") as f:
                json.dump(profiles, f, indent=2, ensure_ascii=False)
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
            with open(PROFILES_PATH, "w", encoding="utf-8") as f:
                json.dump(profiles, f, indent=2, ensure_ascii=False)
        except OSError:
            return f"写入 {PROFILES_PATH} 失败(文件只读?)"
        logger.info(f"人设「{name}」已删除")
        return f"人设「{name}」已删除"

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
        if not _white.get(event.group_id):
            # 没有任何白名单设置的群:不缓存消息
            return
        col = self.collectors.setdefault(event.group_id, _Collector(event.group_id, "grp", self._core()))
        await col.append(event)
        if event.user_id in self._group_white(event.group_id) or event.is_owner:
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
        batch = list(col.buffer) + [event.data]
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
            "ctx.clr": "context.clear",
            "ctx.sum": "context.summary",
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
            if len(parts) < 3:
                await self._reply(event, "用法: .agent.context.summary <总结内容>")
                return
            if uid not in config.owner:
                await self._reply(event, "仅主人可管理上下文")
                return
            # split(None, 2):只切前 2 段,总结内容原样保留(含内部连续空格)
            _, _, content = text.split(None, 2)
            await self._reply(event, await self._core().clear_history(content))
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
