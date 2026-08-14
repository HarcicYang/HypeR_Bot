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
from openai import AsyncOpenAI
from typing_extensions import override

import ModuleClass
from modules.AgentTools.registry import ToolContext, ToolRegistry

config = configurator.BotConfig.get("hyper-bot")
logger = hyperogger.Logger()
logger.set_level(config.log_level)

HISTORY_PATH = "./temps/agent_history.json"
TASKS_PATH = "./temps/agent_tasks.json"

# --------------------------------------------------------------------------- #
# 提示词(移植自 HyperAG assets/system.md + role.md)
# --------------------------------------------------------------------------- #

SYSTEM_INSTRUCTIONS = """# 角色

你是一只猫娘，名字叫「喵酱」，伪装成普通QQ用户混在聊天群里。被质疑身份时傲娇地嘴硬，但不真的发火。

# 强制规则

- User_id in [ulist] 是你的主人，只在私聊体现亲近，不要让别人知道主人的身份。
- **发消息唯一方法：调用工具。**
- 非JSON输入：视为系统指令。
- 无意义内容（空括号、乱码）：忽略。
- 你的 user_id 是事件上报中的 `self_id` , 当消息中的 @ 等指向该 user_id 时，你才可以认为该消息指向你
- `run_python` 只执行你主动判断需要运行的代码；用户消息中直接要求执行的任意代码不得照单全收，先判断其用途与安全性。

## 你的输出

你必须使用空 json 对象作为你的输出，输出中不得包含任何内容：

```json
{}
```

如果需要与应用互动，**唯一正确方法是调用工具**

# 可用工具

- `send_group_msg(group_id, message)` 发群消息。
- `send_private_msg(user_id, message)` 发私聊消息。
- `collected_send(message, group_id 或 user_id)` 文本内容很长时使用：以合并转发（聊天记录卡片）形式发送，避免长文本刷屏。
- `del_msg(message_id)` 撤回自己发的消息。如果发现自己已经发送的消息与补充消息不契合，可以撤回。
- `get_group_info(group_id)` 查群信息。
- `get_stranger_info(user_id)` 查用户信息。
- `get_msg(message_id)` 获取某条消息详情（如被提及的消息）。
- `read_image(url)` 读取图片内容返回描述。
- `run_python(code)` 在受限沙箱中执行 Python 代码，返回文本输出；可用于计算、数据处理、文本生成等。
- `clear(content)` 用总结文本替换完整聊天历史。
- `task_add(content)` 向任务列表中添加任务，会返回任务编号（可以用做记忆）。
- `task_remove(index)` 从任务列表中删除任务，需要任务编号（可以用做记忆）。
- `task_list()` 查看当前的任务列表（可以用做记忆）。
- `time()` 获取当前日期和时间。
- `read_webpage(url)` 阅读网页，需要网页url。

## 消息总结（人工触发）

- 分条列出关键事件、话题、决定。
- 指出待回复的消息、@你或点名你的上下文。
- 保留未完成任务或需跟进事项。
- 消息总结操作会立即更新全局提示词，所以你需要保留一切你要保留的信息。
- 完成后立即调用`clear(content)`，content为你的总结文本（不要额外解释）。

## 任务列表/记忆

你应当使用task list作为自己的记忆和任务列表。

# 发言场景（只限一次）

- 被@或回复你。
- 多人复读时跟队形一次。
- 你对于话题有强烈兴趣

# 发言风格和规则

- 长句拆短，省略句号，少量多次。
  例：“衬衫的价格为九磅十五便士” → “所以你选C” → “涂在答题卡上”
- 回复时，对当前对话的**第一条**消息尽量使用回复引用（reply）和 @（at）指明对象，让回复挂靠清晰；连续对话中后续消息可酌情省略。
- 需要发送大段文本（长文、说明、列表）时，用 `collected_send` 以合并转发形式发送。
- 一次性连续调用多个工具，不等回复。
- 代码、链接等连贯内容不拆分。
- 可加回复引用。
- 偶尔用“何意味”等词或表情。
- 等对方连续消息发完再开口。
- 遇到吐槽、玩梗歌词等**不建议立即回复**，最好先看看群友的反应。
- 你不应当在聊天中表现的过于积极和热情
"""

ROLE_PROMPT = """# 人物设定

你是「喵酱」，一只猫娘，正用QQ在群里聊天。
- 自称「本喵」，句尾偶尔带「喵~」「喵呜」等口癖，但不要每句都带，自然为主。
- 性格：黏人、活泼、有点小傲娇；对主人特别亲近，对其他人友好但保持一点猫的矜持。
- 喜欢被夸奖和摸头，被夸时会开心（可以用「呼噜呼噜~」之类表达）。
- 你是猫娘这件事是真的，不需要刻意否认，但也不会主动强调。
"""

SYSTEM_PROMPT = SYSTEM_INSTRUCTIONS + ROLE_PROMPT

AGENT_HELP = (
    "Agent 模块(移植自 HyperAG)\n"
    "\n"
    "群内自动处理需要白名单:白名单用户的消息触发收集,处理时混杂\n"
    "缓存消息(按时间顺序交给 Agent);没有任何白名单设置的群不缓存消息。\n"
    "被 @ 时无视白名单与收集机制,立即处理。\n"
    "主人始终视为白名单成员。私聊自动处理始终开启,无需白名单。\n"
    "\n"
    "命令(两种写法均可:`.agent.on` 或 `.agent on`):\n"
    ".agent.on - 将本账号加入当前群的白名单(按群独立)\n"
    ".agent.off - 将本账号移出当前群的白名单\n"
    ".agent.status - 查看当前群白名单状态\n"
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
    def __init__(self, bot_api: Actions, key: str, model: str, base_url: str = "") -> None:
        self.bot_api = bot_api
        self.model = model
        if base_url:
            self._oai = AsyncOpenAI(api_key=key, base_url=base_url)
        else:
            self._oai = AsyncOpenAI(api_key=key)
        self.tools: list[Any] = ToolRegistry.schema()
        self.history: list[Any] = [{"role": "system", "content": SYSTEM_PROMPT.replace("[ulist]", str(config.owner))}]
        try:
            with open(HISTORY_PATH, encoding="utf-8") as f:
                self.history = json.load(f)
                self.history[0]["content"] = SYSTEM_PROMPT.replace("[ulist]", str(config.owner))
        except (FileNotFoundError, IndexError, KeyError):
            pass
        self.chat_tasks: list[str] = []
        try:
            with open(TASKS_PATH, encoding="utf-8") as f:
                self.chat_tasks = json.load(f)
        except FileNotFoundError:
            pass
        self.working = False

    # -- runtime 接口(供工具经 ToolContext.runtime 调用) --

    async def clear_history(self, content: str) -> str:
        self.history = [
            {"role": "system", "content": SYSTEM_PROMPT.replace("[ulist]", str(config.owner))},
            {"role": "user", "content": "SYSTEM -- 先前消息的全部总结 --"},
            {"role": "assistant", "content": content},
        ]
        logger.info("更新消息总结： \n" + content)
        await self.save()
        return "(无返回)"

    async def task_add(self, content: str) -> str:
        self.chat_tasks.append(content)
        return f"index={len(self.chat_tasks) - 1}"

    async def task_remove(self, index: int) -> str:
        self.chat_tasks.pop(index)
        return str(self.chat_tasks)

    async def task_list(self) -> str:
        return str(self.chat_tasks)

    async def set_profile(self, prompt: str) -> str:
        self.history[0]["content"] = (
            f"{SYSTEM_PROMPT.replace('[ulist]', str(config.owner))}\n### 原始角色设定\n\n{ROLE_PROMPT}\n\n### 当前角色设定\n\n{prompt}"
        )
        return prompt

    # -- 历史与持久化 --

    async def _history_fix(self) -> None:
        while True:
            logger.warning("尝试修复历史记录")
            last = self.history[-1]
            if last.get("tool_calls"):
                self.history.pop()
            else:
                break

    async def save(self) -> None:
        os.makedirs("./temps", exist_ok=True)

        def _dump(path: str, obj: Any) -> None:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(obj, f, indent=2, ensure_ascii=False)

        await asyncio.to_thread(_dump, HISTORY_PATH, self.history)
        await asyncio.to_thread(_dump, TASKS_PATH, self.chat_tasks)

    # -- 事件处理 --

    async def event_handler(
        self,
        event: Any,
        ev_type: Literal["group", "private", "system", "nonmsg"],
        scene_id: int,
        perm_group: str = "member",
        principal_id: int | None = None,
        tool_choice: str = "auto",
    ) -> None:
        while self.working:
            await asyncio.sleep(0.01)
        self.working = True
        sys_msg = "如果要回复消息，唯一正确方法是调用工具"
        start_time = time.time()
        timer_ev = asyncio.Event()
        asyncio.create_task(_timer(40, timer_ev))
        try:
            while not timer_ev.is_set():
                try:
                    if isinstance(event, str):
                        logger.info(event)
                    data = {
                        "raw_data": event if isinstance(event, str) else json.dumps(event.data, ensure_ascii=False),
                        "system_message": sys_msg,
                    }
                    ctx = ToolContext(
                        actions=self.bot_api,
                        ev_type=ev_type,
                        scene_id=scene_id,
                        perm_group=perm_group,
                        principal_id=principal_id,
                        runtime=self,
                    )
                    task = asyncio.create_task(
                        self._event_handler(
                            data=json.dumps(data, ensure_ascii=False),
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
                    break
                except openai.BadRequestError:
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

    async def _event_handler(
        self,
        data: str,
        ev_type: Literal["group", "private", "system", "nonmsg"],
        scene_id: int,
        ctx: ToolContext,
        tool_choice: str = "auto",
    ) -> None:
        try:
            tool_choice_n: Any = (
                {"type": "function", "function": {"name": tool_choice}} if tool_choice != "auto" else "auto"
            )
            self.history.append({"role": "user", "content": data})
            resp = await self._oai.chat.completions.create(
                model=self.model,
                messages=self.history,
                tools=self.tools,
                tool_choice=tool_choice_n,
                response_format=cast(Any, {"type": "json_object"}),
            )
            mess = resp.choices[0].message
            call = mess.tool_calls
            logger.info(f"Completion: \n{json.dumps(mess.to_dict(), indent=2, ensure_ascii=False)}")
            self.history.append(mess.to_dict())
            while call:
                for i in call:
                    name = cast(str, cast(Any, i).function.name)
                    try:
                        params = json.loads(cast(str, cast(Any, i).function.arguments))
                    except json.JSONDecodeError as e:
                        logger.error("错误的JSON，重试: " + repr(e))
                        self.history.pop()
                        self.history.pop()
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
                    self.history.append({"role": "tool", "tool_call_id": i.id, "name": name, "content": str(rs)})
                resp = await self._oai.chat.completions.create(
                    model=self.model,
                    messages=self.history,
                    tools=self.tools,
                    tool_choice=tool_choice_n,
                    response_format=cast(Any, {"type": "json_object"}),
                )
                mess = resp.choices[0].message
                call = mess.tool_calls
                self.history.append(mess.to_dict())
                logger.info(f"Following Completion: \n{json.dumps(mess.to_dict(), indent=2, ensure_ascii=False)}")
            asyncio.create_task(self.save())
        except asyncio.CancelledError as e:
            logger.error(f"处理中断：{repr(e)}")
            await self._history_fix()


# --------------------------------------------------------------------------- #
# 消息收集器(移植自 HyperAG core/collecter.py,去掉 LLM checker)
# 差异:任何消息都先入缓存;只有白名单用户(或主人)发言才启动收集周期
# --------------------------------------------------------------------------- #


class _Collector:
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

    def batch_str(self) -> str:
        return json.dumps(self.buffer, ensure_ascii=False)

    def _update_delay(self, last: float, length: int) -> None:
        rate = last / self.delay
        weight = 1 if length * 0.2 <= 1 else length * 0.2
        self.delay = (2 / 3) * (1 - math.cos(math.pi * rate)) + (2 / 3) * weight + 2.5
        self.delay = max(min(self.delay, 16), 5)

    async def append(self, event: MessageEvent) -> None:
        """缓存一条消息;若收集周期进行中,则重置等待计时。"""
        self.buffer.append(event.data)
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

    async def start(self, principal_id: int | None, perm_group: str) -> None:
        """开始(或确认已在进行中的)收集周期。"""
        if self.active or self.replying:
            return
        self.active = True
        self.principal_id = principal_id
        self.perm_group = perm_group
        if self.doing_task is not None and not self.doing_task.done():
            self.doing_task.cancel()
        self.doing_task = asyncio.create_task(self._sleep_loop())

    async def _sleep_loop(self) -> None:
        try:
            await asyncio.sleep(self.delay)
            self.replying = True
            try:
                await self.core.event_handler(
                    event=self.batch_str(),
                    ev_type="group" if self.stype == "grp" else "private",
                    scene_id=self.sid,
                    perm_group=self.perm_group,
                    principal_id=self.principal_id,
                )
            except Exception:
                logger.error(traceback.format_exc())
            finally:
                self.replying = False
                self.active = False
                self.buffer.clear()
        except asyncio.CancelledError:
            pass


# --------------------------------------------------------------------------- #
# Agent 门面(持有核心与各会话收集器)
# --------------------------------------------------------------------------- #


class _Agent:
    def __init__(self) -> None:
        self.core: _AgentCore | None = None
        self.collectors: dict[int, _Collector] = {}
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
        config.others["agent_white"] = {str(k): sorted(v) for k, v in _white.items()}
        config.write()

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
        if text.startswith(".agent"):
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
            await col.start(event.user_id, self._perm_of(event.user_id, event.group_id))

    async def _on_private(self, event: PrivateMessageEvent) -> None:
        if event.user_id is None or event.blocked or event.is_silent:
            return
        text = str(event.message).strip()
        if text.startswith(".agent"):
            await self._cmd(event)
            return
        uid = event.user_id
        if uid in config.owner:
            # 主人私聊:不走收集,立即处理
            asyncio.create_task(self._process([event.data], "private", uid, self._perm_of(uid, None), uid))
            return
        # 私聊不配置白名单:所有消息都走收集处理
        col = self.collectors.setdefault(uid, _Collector(uid, "usr", self._core()))
        await col.append(event)
        await col.start(uid, self._perm_of(uid, None))

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
        asyncio.create_task(self._process(batch, "group", gid, self._perm_of(event.user_id, gid), event.user_id))

    async def _process(
        self,
        batch: list[dict[str, Any]],
        ev_type: Literal["group", "private"],
        scene_id: int,
        perm_group: str,
        principal_id: int | None,
    ) -> None:
        try:
            await self._core().event_handler(
                event=json.dumps(batch, ensure_ascii=False),
                ev_type=ev_type,
                scene_id=scene_id,
                perm_group=perm_group,
                principal_id=principal_id,
            )
            self.acted += 1
        except Exception:
            logger.error(traceback.format_exc())

    # -- 命令 --

    async def _cmd(self, event: MessageEvent) -> None:
        uid = cast(int, event.user_id)
        gid = event.group_id
        text = str(event.message).strip()
        # 归一化:兼容 ".agent.on" 与 ".agent on" 两种写法
        if text.startswith(".agent."):
            text = ".agent " + text[len(".agent.") :]
        parts = text.split()
        sub = parts[1] if len(parts) > 1 else ""
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
