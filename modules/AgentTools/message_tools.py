"""消息类工具:发消息、撤回、查消息、合并转发长文本。"""

import asyncio
import dataclasses
import difflib
import json
import math
from typing import Any

from hyperot.v2 import Message, UnknownSegment
from hyperot_adapter_onebot.segments import OneBotSegmentCodec

from modules.AgentTools.registry import AgentToolBase, ForwardNodesArg, SegmentsArg, ToolContext, tool

_codec = OneBotSegmentCodec()


def _unknown(payload: dict[str, Any]) -> UnknownSegment:
    """OneBot 原始段（{type, data}）→ v2 自定义消息段，wire 上原样透传。"""
    return UnknownSegment(wire_type=str(payload.get("type", "unknown")), data=payload.get("data") or {})


# 普通发送的最大序列化长度;超过则拒绝,强制使用 collected_send
MAX_TEXT_LEN = 120
MAX_FORWARD_NODES = 100
MAX_NICKNAME_CHARS = 64
FORWARD_NODE_FIELDS = frozenset({"message", "nickname", "user_id"})
SEGMENT_REQUIRED_FIELDS: dict[str, tuple[str, ...]] = {
    "text": ("text",),
    "at": ("qq",),
    "reply": ("id",),
    "image": ("file",),
}
SEGMENT_ALLOWED_FIELDS: dict[str, tuple[str, ...]] = {
    "text": ("seg", "text"),
    "at": ("seg", "qq"),
    "reply": ("seg", "id"),
    "image": ("seg", "file", "url"),
}
ALL_SEGMENT_FIELDS = ("seg", "text", "qq", "id", "file", "url")


def _suggest_name(name: str, candidates: tuple[str, ...]) -> str | None:
    normalized = name.strip().casefold()
    for candidate in candidates:
        if normalized == candidate.casefold():
            return candidate
    matches = difflib.get_close_matches(normalized, list(candidates), n=1, cutoff=0.5)
    return matches[0] if matches else None


def _validate_message(message: Any) -> str | None:
    """返回按消息段索引聚合的参数错误；消息合法时返回 None。"""
    if not isinstance(message, list):
        return "调用不合法：message 必须是消息段数组"
    if not message:
        return "调用不合法：message 不能为空"

    errors: list[str] = []
    for index, segment in enumerate(message):
        prefix = f"index{index}"
        if not isinstance(segment, dict):
            errors.append(f"{prefix}: 消息段必须是对象")
            continue

        seg_type = segment.get("seg")
        if seg_type is None:
            errors.append(f"{prefix}: 未指定 seg")
        elif not isinstance(seg_type, str):
            errors.append(f"{prefix}: seg 必须是字符串")
        elif seg_type not in SEGMENT_REQUIRED_FIELDS:
            suggestion = _suggest_name(seg_type, tuple(SEGMENT_REQUIRED_FIELDS))
            hint = f'，你可能是指 "{suggestion}"' if suggestion else ""
            errors.append(f'{prefix}: 未知的段类型 "{seg_type}"{hint}')

        if isinstance(seg_type, str) and seg_type in SEGMENT_REQUIRED_FIELDS:
            allowed_fields = SEGMENT_ALLOWED_FIELDS[seg_type]
            for field in SEGMENT_REQUIRED_FIELDS[seg_type]:
                if field not in segment or segment[field] is None:
                    errors.append(f'{prefix}: seg "{seg_type}" 需要 "{field}" 字段，但是你没有提供')
        else:
            allowed_fields = ALL_SEGMENT_FIELDS

        for field in segment:
            if field in allowed_fields:
                continue
            suggestion = _suggest_name(field, allowed_fields)
            hint = f'，你可能是指 "{suggestion}"' if suggestion else ""
            errors.append(f'{prefix}: 未知的字段 "{field}"{hint}')

    if errors:
        return "调用不合法：\n" + "\n".join(errors)
    return None


def _positive_int_error(name: str, value: Any) -> str | None:
    if isinstance(value, bool):
        return f"调用不合法：{name} 必须是正整数，不能使用布尔值"
    if not isinstance(value, int) or value <= 0:
        return f"调用不合法：{name} 必须是正整数，当前值为 {value!r}"
    return None


async def _build_message(ctx: ToolContext, raw_message: Any) -> tuple[Message | None, str | None]:
    if err := _validate_message(raw_message):
        return None, err
    try:
        message = await ctx.create_msg(raw_message)
    except Exception as exc:
        return None, f"消息参数不合法：{exc}"
    if not str(message):
        return None, "调用不合法：message 不能为空"
    return message, None


def _check_len(msg: Message) -> str | None:
    """消息序列化后 str() 长度超过 MAX_TEXT_LEN 时返回错误信息(强制改用合并转发)。"""
    if len(str(msg)) > MAX_TEXT_LEN:
        return f"消息过长(序列化后 {len(str(msg))} 字符,上限 {MAX_TEXT_LEN})，请改用 collected_send 以合并转发形式发送"
    return None


def _strip_error_prefix(error: str) -> str:
    for prefix in ("调用不合法：", "消息参数不合法："):
        if error.startswith(prefix):
            return error[len(prefix) :]
    return error


def _node_user_id(value: Any, default: str) -> tuple[str | None, str | None]:
    if value is None or value == "":
        return default, None
    if isinstance(value, bool):
        return None, "user_id 必须是正整数"
    text = str(value).strip()
    if not text.isdigit() or int(text) <= 0:
        return None, f"user_id 必须是正整数，当前值为 {value!r}"
    return text, None


async def _build_forward_nodes(
    ctx: ToolContext,
    message: Any,
    nodes: Any,
) -> tuple[list[dict[str, Any]] | None, str | None]:
    if (message is None) == (nodes is None):
        return None, "调用不合法：message 与 nodes 必须且只能提供一个"
    if message is not None:
        built, error = await _build_message(ctx, message)
        if error:
            return None, error
        assert built is not None
        return [
            {
                "type": "node",
                "data": {
                    "user_id": str(ctx.self_id or ctx.principal_id or 0),
                    "nickname": "",
                    "content": _codec.encode_segments(built),
                },
            }
        ], None

    if not isinstance(nodes, list):
        return None, "调用不合法：nodes 必须是节点数组"
    if not nodes:
        return None, "调用不合法：nodes 不能为空"
    if len(nodes) > MAX_FORWARD_NODES:
        return None, f"调用不合法：nodes 最多 {MAX_FORWARD_NODES} 个节点"

    result: list[dict[str, Any]] = []
    for index, node in enumerate(nodes):
        if not isinstance(node, dict):
            return None, f"调用不合法：nodes[{index}] 必须是对象"
        unknown = sorted(set(node) - FORWARD_NODE_FIELDS)
        if unknown:
            return None, f"调用不合法：nodes[{index}] 含未知字段 {', '.join(unknown)}"
        if "message" not in node:
            return None, f"调用不合法：nodes[{index}].message 不能为空"
        built, error = await _build_message(ctx, node.get("message"))
        if error:
            return None, f"调用不合法：nodes[{index}].message {_strip_error_prefix(error)}"

        user_id, error = _node_user_id(node.get("user_id"), str(ctx.self_id or ctx.principal_id or 0))
        if error:
            return None, f"调用不合法：nodes[{index}].{error}"
        nickname = node.get("nickname", "")
        if nickname is None:
            nickname = ""
        if not isinstance(nickname, str):
            return None, f"调用不合法：nodes[{index}].nickname 必须是字符串"
        nickname = nickname.strip()
        if len(nickname) > MAX_NICKNAME_CHARS:
            return None, f"调用不合法：nodes[{index}].nickname 最多 {MAX_NICKNAME_CHARS} 个字符"
        assert built is not None and user_id is not None
        result.append(
            {
                "type": "node",
                "data": {
                    "user_id": user_id,
                    "nickname": nickname,
                    "content": _codec.encode_segments(built),
                },
            }
        )
    return result, None


class MessageTools(AgentToolBase):
    @tool(group="qq", sub_visible=False)
    async def send_group_msg(self, ctx: ToolContext, group_id: int, message: SegmentsArg) -> Any:
        """向指定群发送消息。

        - group_id: 目标群号，与事件中的 group_id 对应
        - message: 消息段数组（text/at/reply/image）
        - 消息序列化后超过 120 字符会被拒绝，长文本必须改用 collected_send

        返回值：
        - 成功时返回“发送成功”和可用于引用、撤回的 message_id
        - 上游明确失败时返回“发送失败”及 status、retcode、原因
        """
        if err := _positive_int_error("group_id", group_id):
            return err
        new_mess, err = await _build_message(ctx, message)
        if err:
            return err
        assert new_mess is not None
        if err := _check_len(new_mess):
            return err
        await asyncio.sleep(math.log(len(str(new_mess)) + 3))
        result = await ctx.actions.group(str(group_id)).send(new_mess)
        return f"群消息发送成功：group_id={group_id}，message_id={result.message_id}"

    @tool(group="qq", sub_visible=False)
    async def send_private_msg(self, ctx: ToolContext, user_id: int, message: SegmentsArg) -> Any:
        """向指定用户私聊发送消息（需有对方好友）。

        - user_id: 目标用户 QQ 号
        - message: 消息段数组（text/at/reply/image）
        - 消息序列化后超过 120 字符会被拒绝，长文本必须改用 collected_send

        返回值：
        - 成功时返回“发送成功”和可用于引用、撤回的 message_id
        - 上游明确失败时返回“发送失败”及 status、retcode、原因
        """
        if err := _positive_int_error("user_id", user_id):
            return err
        new_mess, err = await _build_message(ctx, message)
        if err:
            return err
        assert new_mess is not None
        if err := _check_len(new_mess):
            return err
        result = await ctx.actions.user(str(user_id)).send(new_mess)
        return f"私聊消息发送成功：user_id={user_id}，message_id={result.message_id}"

    @tool(group="qq", sub_visible=False)
    async def poke(self, ctx: ToolContext, user_id: int, group_id: int | None = None) -> str:
        """戳一戳指定用户。

        - user_id: 目标用户 QQ 号
        - group_id: 在群聊中戳人时传目标群号；私聊戳人时省略

        返回值：
        - 成功时返回“戳一戳请求已发送”
        - 上游明确失败时返回“戳一戳失败”及 status、retcode、原因
        """
        if err := _positive_int_error("user_id", user_id):
            return err
        if group_id is not None and (err := _positive_int_error("group_id", group_id)):
            return err
        if group_id is None:
            await ctx.actions.user(str(user_id)).poke(user_id)
            return f"戳一戳请求已发送：user_id={user_id}"
        await ctx.actions.group(str(group_id)).poke(user_id)
        return f"戳一戳请求已发送：group_id={group_id}，user_id={user_id}"

    @tool(group="qq", sub_visible=False)
    async def collected_send(
        self,
        ctx: ToolContext,
        message: SegmentsArg | None = None,
        group_id: int | None = None,
        user_id: int | None = None,
        nodes: ForwardNodesArg | None = None,
    ) -> Any:
        """以合并转发（聊天记录卡片）形式发送消息，避免长文本刷屏。

        - message: 单节点快捷方式，消息段数组（与 nodes 二选一）
        - nodes: 多节点数组，每项格式为 {"user_id": "QQ号", "nickname": "昵称", "message": 消息段数组}；
          user_id 和 nickname 可省略，user_id 省略时使用 Bot 自身 QQ；最多 100 个节点
        - group_id / user_id: 目标群号或用户 QQ 号，必须且只能提供一个
        - 消息文本较长（超过 120 字符）时使用本工具

        返回值：
        - 成功时返回“合并转发发送成功”和 message_id
        - 上游明确失败时返回“合并转发发送失败”及 status、retcode、原因
        """
        if (group_id is None) == (user_id is None):
            return "调用不合法：group_id 与 user_id 必须且只能提供一个"
        if group_id is not None and (err := _positive_int_error("group_id", group_id)):
            return err
        if user_id is not None and (err := _positive_int_error("user_id", user_id)):
            return err
        node_payloads, err = await _build_forward_nodes(ctx, message, nodes)
        if err:
            return err
        assert node_payloads is not None
        fwd = Message(_unknown({"type": "forward", "data": {"content": node_payloads}}))
        if group_id is not None:
            result = await ctx.actions.group(str(group_id)).send(fwd)
            return f"合并转发发送成功：group_id={group_id}，message_id={result.message_id}"
        assert user_id is not None
        result = await ctx.actions.user(str(user_id)).send(fwd)
        return f"合并转发发送成功：user_id={user_id}，message_id={result.message_id}"

    @tool(group="qq", sub_visible=False)
    async def set_group_reaction(
        self,
        ctx: ToolContext,
        group_id: int,
        message_id: int,
        code: int | None = None,
        emoji: str | None = None,
        is_add: bool = True,
    ) -> str:
        """对指定群消息设置表情回应。

        - group_id: 目标群号
        - message_id: 目标消息 id
        - code: QQ 小黄脸表情 ID(qface)，例如 76 表示赞；与 emoji 二选一
        - emoji: emoji 字符本身；与 code 二选一
        - is_add: true 表示添加回应，false 表示移除回应

        怎么做？

        你应当对于看到的消息，根据你的感受使用该工具。该工具并不烦人，可以较多的使用。

        返回值：
        - 成功时返回“表情回应设置请求已发送”
        - 上游明确失败时返回失败原因
        """
        if (code is None) == (emoji is None):
            return "调用不合法：code(qface ID) 与 emoji 必须且只能提供一个"
        if err := _positive_int_error("group_id", group_id):
            return err
        params: dict[str, Any] = {"group_id": group_id, "message_id": message_id, "is_add": is_add}
        if code is not None:
            params["code"] = code
        else:
            params["emoji"] = emoji
        await ctx.actions.raw("group_reaction", params)
        action = "设置" if is_add else "移除"
        target = f"code={code}" if code is not None else f"emoji={emoji}"
        return f"表情回应{action}请求已发送：group_id={group_id}，message_id={message_id}，{target}"

    @tool(group="qq", sub_visible=False)
    async def del_msg(self, ctx: ToolContext, message_id: int) -> str:
        """撤回消息（如果你没有管理员，就只可撤回自己发送的）。

        - message_id: 目标消息 id，与发送回报或事件中的 message_id 对应

        返回值：
        - 返回“撤回请求已发送”；协议接口不提供成功确认
        """
        await ctx.actions.message(str(message_id)).recall()
        return f"撤回请求已发送：message_id={message_id}"

    @tool(group="qq", sub_visible=False, preserve=True)
    async def get_msg(self, ctx: ToolContext, message_id: int) -> Any:
        """获取消息详情（含发送者、时间、消息段），可用于查看被提及的未收到消息。

        - message_id: 目标消息 id

        返回值：
        - 成功时返回“获取消息成功”和协议端返回的消息详情
        - 上游明确失败时返回失败原因
        """
        message = await ctx.actions.message(str(message_id)).fetch()
        detail = json.dumps([dataclasses.asdict(seg) for seg in message], ensure_ascii=False, default=str)
        return f"获取消息成功：message_id={message_id}，详情={detail}"

    @tool(group="qq", sub_visible=False, preserve=True)
    async def resolve_forward(self, ctx: ToolContext, forward_id: str) -> str:
        """解析合并转发消息，返回每条消息的发送者昵称与内容（段 JSON）。

        - forward_id: 合并转发 id，来自事件中 forward 段的 data.id

        返回值：
        - 成功时返回合并转发中每条消息的发送者昵称与内容
        - 无法取得内容时明确说明请求已发送但未返回内容
        """
        result = await ctx.runtime.resolve_forward(forward_id)
        return result or "合并转发解析请求已发送，但协议端未返回内容"

    @tool(group="qq", sub_visible=False)
    async def profile_like(self, ctx: ToolContext, user_id: int, times: int) -> str:
        """向指定用户的 QQ 名片进行点赞

        - user_id: 目标用户 QQ 号
        - times: 点赞次数，必须为正整数，不建议超过10

        返回值：
        - 成功时返回“点赞请求已发送”
        - 上游明确失败时返回失败原因
        """

        if err := _positive_int_error("user_id", user_id):
            return err
        await ctx.actions.raw("send_like", {"user_id": user_id, "times": times})

        return f"点赞请求已发送：user_id={user_id}，times={times}"
