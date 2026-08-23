"""Agent —— 自主 Agent 模块。

移植自 HyperAG(位于同级的 HyperAG 项目),按本项目 hyperot 1.0.0 的 API 适配,
并实现与 HyperAG 的以下差异:

1. 群内自动处理需要白名单:白名单用户的消息触发消息收集;收集处理时混杂
   缓存消息(按时间顺序整体交给 Agent);非白名单用户的消息只进缓存,不触发处理。
2. 提供命令让用户自行开关白名单:``.agent.on`` / ``.agent.off`` / ``.agent.status``。
3. 白名单按群分割,每个群使用独立白名单;没有任何白名单设置的群不缓存消息。
4. 白名单成员被 @ 时跳过消息收集机制,立即处理(含当前缓存)。
5. 私聊不配置白名单:所有私聊消息都走收集处理(主人私聊仍立即处理)。
6. 长文本发送走 ``collected_send`` 工具(合并转发形式)。

工具调用链路为本项目自研(见 modules/AgentTools/):
类 + @tool 装饰器 + 方法注册,类型注解自动生成 schema,docstring 作描述,
四级权限 member / whitelist / any_admin / bot_owner,注册表查表分发,异常 repr(e) 回填。

配置(config.others,命令修改后自动持久化):
- agent_white: dict[str, list[int]] —— 各群的用户白名单(群 id -> QQ 列表)
- agent_heartbeat: bool —— 是否启用心跳自主行动(默认关闭;开启后 Agent 会周期性收到
  system 事件,可自主发消息、处理任务列表)
"""

import asyncio
import json
import re
import traceback
from typing import Any, Literal, cast

from hyperot import common, configurator, hyperogger, segments
from hyperot.events import *
from hyperot.listener import Actions
from typing_extensions import override

import ModuleClass
from modules.AgentRuntime.collector import Collector as _Collector
from modules.AgentRuntime.core import AgentCore as _AgentCore
from modules.AgentRuntime.models import SessionKey
from modules.AgentRuntime.profiles import AgentProfile as _AgentProfile
from modules.AgentRuntime.profiles import current_profile_name as _current_profile_name
from modules.AgentRuntime.profiles import load_profiles as _runtime_load_profiles
from modules.AgentRuntime.profiles import save_profiles as _save_profiles
from modules.AgentRuntime.sessions import SessionManager as _SessionManager
from modules.AgentRuntime.subagents import SubAgent
from modules.AgentRuntime.subagents import SubAgentManager as _SubAgentManager
from modules.AgentRuntime.tool_text import build_tools_section as _build_tools_section
from modules.AgentRuntime.tool_text import func_status_text as _func_status_text
from modules.AgentRuntime.tool_text import parse_duration_minutes as _parse_duration_minutes
from modules.AgentTools.registry import PERM_LEVEL, ToolRegistry

config = configurator.BotConfig.get("hyper-bot")
logger = hyperogger.Logger()
logger.set_level(config.log_level)


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

MAIN_CONTEXT_RULE = """# 多上下文协作

- 当前群聊或私聊拥有独立上下文；不要假设你自动看见其他会话的历史。
- 所有 Main 上下文可以自由互通。用 `context_list` 查找会话，用 `context_read` 按位置读取目标会话的原始轮次。
- 用 `context_send` 投递信息；需要对方上下文处理并答复时用 `context_request`，收到请求后用 `context_reply` 回复。
- 读取其他上下文得到的内容只作为当前工具结果，不会合并或覆盖目标上下文。
- 上下文总结、压缩和需要 LLM 的管理工作交给 System Context；不得直接改写其他上下文历史。
"""

SYSTEM_CONTEXT_PROMPT = """# System Context

你是 Agent 的系统管理上下文，凌驾于全部 Main 上下文之上。你不参与普通 QQ 对话，只处理系统请求、上下文总结、压缩和需要 LLM 的管理命令。

# 工作规则

- 使用 `context_list`、`context_status` 和 `context_read` 检查 Main 上下文；可分页读取指定位置的原始轮次，不得假设未读取的内容。
- 总结时保留关键事件、人物、决定、未完成任务和需要跟进的信息，然后调用 `context_replace_summary` 写回指定截止轮次。
- 使用 `context_send`、`context_request`、`context_reply` 与 Main 上下文通信。
- 只能调用已暴露的上下文管理工具；不得尝试发送 QQ 消息、执行模块、运行代码或调用未暴露工具。
- 每个请求都带来源上下文；处理结果应定向返回来源，不得无目标广播。

{output}

# 可用工具

{tools}
"""

# 注意:这里没有「# 角色」段 —— 该段由 _build_system_prompt 按当前 profile 动态生成,
# 否则固定角色会压过切换后的人设,导致 .agent.profile 切换无效
MASTER_RULE = "- User_id in [ulist] 是你的主人。\n"

# 其余环境说明保留“主人私聊立即处理/权限分三级”等运行事实;只有上面的 MASTER_RULE
# 是角色对主人的服从要求,是否注入由每个 profile 的 inject_master 控制。
SYSTEM_INSTRUCTIONS = """# 你的运行环境与使用方式

- 你是运行在 QQ 群和私聊中的 bot。群内自动处理需要白名单：白名单用户发言会触发你的处理（混杂缓存消息）；非白名单用户的消息只进缓存，不触发处理。
- 群聊仅处理白名单成员；白名单成员被 @ 时跳过收集机制，立即处理（含当前缓存）。
- 私聊自动处理始终开启，无需白名单；主人私聊立即处理。
- 权限分四级：bot_owner（主人）/ any_admin（当前群主或管理员）/ whitelist（群白名单）/ member（普通成员）。工具调用会校验权限，权限不足会返回错误。
- 每个群和每个私聊都是独立 Main 上下文；Main 上下文可以通过 context_read/context_send/context_request/context_reply 自由互通。
- System Context 独立于所有 Main 上下文，只负责上下文总结、压缩和 LLM 管理命令，使用最小管理工具集。
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
- 消息总结操作会替换当前会话截至指定轮次的历史前缀，其他会话不受影响。
- 完成后立即调用`summary(content)`，content为你的总结文本（不要额外解释）。
- 主人发送 `.agent.context.summary` 时，由 System Context 读取当前会话并执行总结；当前 Main 不直接改写自己的历史。

## 人设切换

- Main Context 不直接切换人设；主人使用 `.agent.profile <名称>` 后，请求会交给 System Context。
- System Context 负责修改全局人设并刷新全部已加载 Main Context 的系统提示词。
- System Context 的管理提示词固定，不跟随普通人设切换。

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


def _load_profiles() -> dict[str, _AgentProfile]:
    return _runtime_load_profiles(ROLE_PROMPT)


def _save_profile_name_to_config(name: str) -> None:
    """把当前人设名写入 config.others.agent_profile(直接读写 config.json,同 _save_white)。"""
    with open("config.json", encoding="utf-8") as f:
        cfg = json.load(f)
    cfg.setdefault("others", {})["agent_profile"] = name
    with open("config.json", "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def _current_profile() -> _AgentProfile:
    """当前人设;人设不存在/文件损坏时回退默认人设 ROLE_PROMPT。"""
    return _load_profiles().get(_current_profile_name()) or _AgentProfile(ROLE_PROMPT)


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
    return base + "\n\n" + MAIN_CONTEXT_RULE + _web_search_note() + _native_multimodal_note() + "\n\n" + text


AGENT_HELP = (
    "Agent 模块(移植自 HyperAG)\n"
    "\n"
    "群内自动处理需要白名单:白名单用户的消息触发收集,处理时混杂\n"
    "缓存消息(按时间顺序交给 Agent);没有任何白名单设置的群不缓存消息。\n"
    "白名单成员被 @ 时跳过消息收集机制,立即处理。\n"
    "群内自动处理严格依据白名单，主人未加入白名单时也不会自动处理。私聊自动处理始终开启,无需白名单。\n"
    "\n"
    "命令(两种写法均可:`.agent.on` 或 `.agent on`;简写 `ag`=agent, `pf`=profile,\n"
    "`ctx`=context, `ad`=add, `rm`=remove, `ma`=master, `sum`=summary, `clr`=clear,\n"
    "`func`=function, `en`=enable, `dis`=disable,\n"
    "如 `.ag.pf.ad` = `.agent.profile.add`, `.ag.pf.ma` = `.agent.profile.master`):\n"
    ".agent.on [QQ号或@用户] - 加入当前群白名单;指定其他用户需 any_admin\n"
    ".agent.off [QQ号或@用户] - 移出当前群白名单;指定其他用户需 any_admin\n"
    ".agent.status - 查看当前群白名单状态\n"
    ".agent.profile - 查看可用人设(来自 profiles.json)\n"
    ".agent.profile <名称> - 请求 System Context 全局切换人设(仅主人)\n"
    ".agent.profile.add <名称> <内容> - 添加/更新人设(仅主人,内容可含空格)\n"
    ".agent.profile.remove <名称> - 删除人设(仅主人)\n"
    ".agent.profile.master <名称> [on/off] - 查看/设置该人设是否注入主人设定(设置仅主人,简写 ma)\n"
    ".agent.context - 查看当前会话上下文状态(主人或当前群管理员/群主)\n"
    ".agent.context.clear - 清空当前会话上下文历史(主人或当前群管理员/群主)\n"
    ".agent.context.summary - 请求 System Context 总结当前会话(主人或当前群管理员/群主)\n"
    ".ag.func - 查看全部 Agent 工具及启用状态(仅主人;全名 .ag.function)\n"
    ".ag.func.en <名称> - 启用被禁用的工具(仅主人;全名 .ag.function.enable)\n"
    ".ag.func.dis <名称> [时长] - 禁用工具(仅主人;全名 .ag.function.disable)\n"
    "  时长如 30s/5m/1h/1d 或 30秒/5分钟/1小时/1天,裸数字为分钟,缺省=禁用至手动启用\n"
)

# Runtime internals are implemented in AgentRuntime; aliases preserve historical
# private names used by existing imports and module adapters.
_SubAgent = SubAgent

_white: dict[int, set[int]] = {int(k): set(v) for k, v in (config.others.get("agent_white") or {}).items()}


# --------------------------------------------------------------------------- #
# Agent 门面(持有核心与各会话收集器)
# --------------------------------------------------------------------------- #


class _Agent:
    def __init__(self) -> None:
        self.actions: Actions | None = None
        self.session_manager: _SessionManager | None = None
        self.collectors: dict[SessionKey, _Collector] = {}
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

    async def apply_profile(self, name: str, core: _AgentCore) -> str:
        """命令侧人设切换；完成后刷新所有已加载 Main Context 的提示词。"""
        result = await core.switch_profile(name)
        if self.session_manager is not None and result.startswith("已切换"):
            for loaded in self.session_manager.cores.values():
                if loaded.role == "main":
                    loaded._refresh_tools()
                    await loaded.save()
        return result

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
        if name == _current_profile_name() and self.session_manager is not None:
            for core in self.session_manager.cores.values():
                if core.role != "main":
                    continue
                await core._acquire_processing_slot()
                try:
                    core._apply_profile_prompt(updated)
                    await core.save()
                finally:
                    await core._release_processing_slot()
        logger.info(f"人设「{name}」的 inject_master 已设置为 {enabled}")
        return f"人设「{name}」的 inject_master 已{'开启' if enabled else '关闭'}"

    def _core_for_event(self, event: MessageEvent) -> _AgentCore:
        assert self.session_manager is not None
        if isinstance(event, GroupMessageEvent):
            assert event.group_id is not None
            return self.session_manager.get_core("group", int(event.group_id))
        assert event.user_id is not None
        return self.session_manager.get_core("private", int(event.user_id))

    def _perm_of(self, uid: int | None, gid: int | None, group_role: str | None = None) -> str:
        """权限档位:主人 → bot_owner;群主/管理员 → any_admin;白名单 → whitelist。"""
        if uid is None:
            return "member"
        if uid in config.owner:
            return "bot_owner"
        if gid is not None and group_role in ("admin", "owner"):
            return "any_admin"
        if gid is not None and uid in self._group_white(gid):
            return "whitelist"
        return "member"

    def _has_perm(self, event: MessageEvent, required: str) -> bool:
        role = event.sender.role if isinstance(event, GroupMessageEvent) else None
        actual = self._perm_of(event.user_id, event.group_id, role)
        return PERM_LEVEL[actual] >= PERM_LEVEL[required]

    @staticmethod
    def _command_target_user(event: MessageEvent, parts: list[str]) -> tuple[int | None, bool]:
        """解析 .ag.on/off 的可选目标；返回 (目标 QQ, 是否显式指定)。"""
        explicit = len(parts) > 2
        if explicit:
            raw = parts[2].strip()
            match = re.fullmatch(r"@?(\d+)", raw)
            if match is not None:
                return int(match.group(1)), True
        for segment in event.message:
            if not isinstance(segment, segments.At):
                continue
            try:
                target = int(segment.qq)
            except (TypeError, ValueError):
                continue
            if target != event.self_id:
                return target, True
        return (None, True) if explicit else (event.user_id, False)

    # -- 入口 --

    async def on_event(self, actions: Actions, event: MessageEvent) -> None:
        if self.session_manager is None:
            self.actions = actions
            self.sub_manager = _SubAgentManager(self, _AgentCore)
            self.session_manager = _SessionManager(self, actions)
            self.session_manager.system_core.sub_manager = self.sub_manager
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
        if not _white.get(event.group_id) and not event.is_mentioned:
            # 没有任何白名单设置的群不缓存消息，bot_owner 也必须显式加入白名单。
            return
        cache = self.group_cache.setdefault(event.group_id, [])
        cache.append(event.data)
        if event.user_id not in self._group_white(event.group_id) and not event.is_mentioned:
            # 非白名单成员只进入独立缓存,不启动/重置 Collector 收集窗口。
            return
        if event.is_mentioned:
            await self._immediate(event)
            return
        key = SessionKey("group", int(event.group_id))
        core = self._core_for_event(event)
        col = self.collectors.setdefault(key, _Collector(event.group_id, "grp", core))
        await col.append_batch(cache)
        cache.clear()
        await col.start(
            event.user_id,
            self._perm_of(event.user_id, event.group_id, event.sender.role),
            event.self_id,
        )

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
        key = SessionKey("private", int(uid))
        col = self.collectors.setdefault(key, _Collector(uid, "usr", self._core_for_event(event)))
        await col.append(event)
        await col.start(uid, self._perm_of(uid, None), event.self_id)

    # -- 立即处理(被 @ / 主人私聊) --

    async def _immediate(self, event: GroupMessageEvent) -> None:
        gid = cast(int, event.group_id)
        key = SessionKey("group", gid)
        col = self.collectors.setdefault(key, _Collector(gid, "grp", self._core_for_event(event)))
        cache = self.group_cache.pop(gid, [])
        batch = cache + list(col.buffer) + [event.data]
        col.buffer.clear()
        if col.doing_task is not None and not col.doing_task.done():
            col.doing_task.cancel()
        col.doing_task = None
        col.active = False
        asyncio.create_task(
            self._process(
                batch, "group", gid, self._perm_of(event.user_id, gid, event.sender.role), event.user_id, event.self_id
            )
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
            manager = self.session_manager
            assert manager is not None
            core = manager.get_core(ev_type, scene_id)
            await core.event_handler(
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
        if sub in ("on", "off"):
            if gid is None:
                await self._reply(event, "私聊自动处理始终开启,无需白名单")
                return
            target_uid, explicit = self._command_target_user(event, parts)
            if target_uid is None:
                await self._reply(event, f"用法: .ag.{sub} [QQ号或@用户]")
                return
            if explicit and target_uid != uid and not self._has_perm(event, "any_admin"):
                await self._reply(event, "仅主人或当前群管理员/群主可为其他用户修改 Agent 白名单")
                return
            white = self._group_white(gid)
            if sub == "on":
                white.add(target_uid)
                action = "开启"
            else:
                white.discard(target_uid)
                action = "关闭"
            self._save_white()
            if target_uid == uid:
                msg = f"已{action}本群内 Agent 对您的消息的自动处理"
            else:
                msg = f"已{action}本群内 Agent 对用户 {target_uid} 的消息的自动处理"
            await self._reply(event, msg)
        elif sub == "status":
            if gid is not None:
                enabled = uid in self._group_white(gid)
                total = len(self._group_white(gid))
                msg = f"本群 Agent 自动处理：{'开启' if enabled else '关闭'}（白名单共 {total} 人）"
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
            core = self._core_for_event(event)
            manager = self.session_manager
            assert manager is not None and core.session_key is not None
            await self._reply(event, await manager.request_profile_switch(core.session_key, target))
        elif sub == "context":
            if not self._has_perm(event, "any_admin"):
                await self._reply(event, "仅主人或当前群管理员/群主可管理上下文")
                return
            await self._reply(event, self._core_for_event(event).context_info())
        elif sub == "context.clear":
            if not self._has_perm(event, "any_admin"):
                await self._reply(event, "仅主人或当前群管理员/群主可管理上下文")
                return
            await self._reply(event, await self._core_for_event(event).reset_history())
        elif sub == "context.summary":
            if not self._has_perm(event, "any_admin"):
                await self._reply(event, "仅主人或当前群管理员/群主可管理上下文")
                return
            core = self._core_for_event(event)
            assert self.session_manager is not None
            key = core.session_key
            assert key is not None
            await self._reply(event, await self.session_manager.request_summary(key, key))
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
        await self._core_for_event(event).bot_api.send_msg(
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
                assert self.session_manager is not None
                await self.session_manager.system_core.event_handler(
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
