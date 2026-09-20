"""消息类工具:发消息、撤回、查消息、合并转发长文本。"""

import asyncio
import difflib
import json
import math
from typing import Any

from hyperot import common, segments

from modules.AgentTools.registry import AgentToolBase, SegmentsArg, ToolContext, tool

# 普通发送的最大序列化长度;超过则拒绝,强制使用 collected_send
MAX_TEXT_LEN = 120
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


async def _build_message(ctx: ToolContext, raw_message: Any) -> tuple[common.Message | None, str | None]:
    if err := _validate_message(raw_message):
        return None, err
    try:
        message = await ctx.create_msg(raw_message)
    except Exception as exc:
        return None, f"消息参数不合法：{exc}"
    if not str(message):
        return None, "调用不合法：message 不能为空"
    return message, None


def _check_len(msg: common.Message) -> str | None:
    """消息序列化后 str() 长度超过 MAX_TEXT_LEN 时返回错误信息(强制改用合并转发)。"""
    if len(str(msg)) > MAX_TEXT_LEN:
        return f"消息过长(序列化后 {len(str(msg))} 字符,上限 {MAX_TEXT_LEN})，请改用 collected_send 以合并转发形式发送"
    return None


def _ret_succeeded(ret: common.Ret[Any]) -> bool:
    return ret.status == "ok" or (ret.status is None and ret.ret_code in (None, 0))


def _ret_failure(action: str, ret: common.Ret[Any]) -> str:
    details: list[str] = []
    if ret.status is not None:
        details.append(f"status={ret.status}")
    if ret.ret_code is not None:
        details.append(f"retcode={ret.ret_code}")
    reason = ret.raw.get("message") or ret.raw.get("wording")
    if reason:
        details.append(f"原因={reason}")
    detail_text = "，".join(details) if details else "协议端未返回详情"
    return f"{action}失败：{detail_text}"


def _send_result(action: str, target: str, ret: common.Ret[Any]) -> str:
    if not _ret_succeeded(ret):
        return _ret_failure(action, ret)
    message_id = getattr(ret.data, "message_id", None)
    if message_id is None:
        return f"{action}请求已发送：{target}，但协议端未返回 message_id"
    return f"{action}成功：{target}，message_id={message_id}"


async def _custom_ret(echo: Any) -> common.Ret[Any]:
    if isinstance(echo, str):
        return await common.Ret.fetch(echo)
    if isinstance(echo, dict) and ("status" in echo or "retcode" in echo):
        return common.Ret(echo)
    return common.Ret({"status": "ok", "retcode": 0, "data": echo})


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
        ret = await ctx.actions.send_msg(message=new_mess, group_id=group_id)
        return _send_result("群消息发送", f"group_id={group_id}", ret)

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
        ret = await ctx.actions.send_msg(message=new_mess, user_id=user_id)
        return _send_result("私聊消息发送", f"user_id={user_id}", ret)

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
        echo = await ctx.actions.custom.send_poke(user_id=user_id, group_id=group_id or 0)
        ret = await _custom_ret(echo)
        if not _ret_succeeded(ret):
            return _ret_failure("戳一戳", ret)
        if group_id is None:
            return f"戳一戳请求已发送：user_id={user_id}"
        return f"戳一戳请求已发送：group_id={group_id}，user_id={user_id}"

    @tool(group="qq", sub_visible=False)
    async def collected_send(
        self, ctx: ToolContext, message: SegmentsArg, group_id: int | None = None, user_id: int | None = None
    ) -> Any:
        """以合并转发（聊天记录卡片）形式发送消息，避免长文本刷屏。

        - message: 消息段数组，整条消息作为一个节点（不拆分，保留 text/at/reply 等全部段）
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
        new_mess, err = await _build_message(ctx, message)
        if err:
            return err
        assert new_mess is not None
        nodes = [
            segments.CustomNode(
                user_id=str(ctx.self_id or ctx.principal_id or 0), nickname="", content=new_mess
            ).to_json()
        ]
        fwd = common.Message(segments.Forward(content=nodes))
        if group_id is not None:
            ret = await ctx.actions.send_msg(message=fwd, group_id=group_id)
            return _send_result("合并转发发送", f"group_id={group_id}", ret)
        assert user_id is not None
        ret = await ctx.actions.send_msg(message=fwd, user_id=user_id)
        return _send_result("合并转发发送", f"user_id={user_id}", ret)

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
        echo = await ctx.actions.custom.group_reaction(**params)
        action = "设置" if is_add else "移除"
        target = f"code={code}" if code is not None else f"emoji={emoji}"
        ret = await _custom_ret(echo)
        if not _ret_succeeded(ret):
            return _ret_failure(f"表情回应{action}", ret)
        return f"表情回应{action}请求已发送：group_id={group_id}，message_id={message_id}，{target}"

    @tool(group="qq", sub_visible=False)
    async def del_msg(self, ctx: ToolContext, message_id: int) -> str:
        """撤回消息（如果你没有管理员，就只可撤回自己发送的）。

        - message_id: 目标消息 id，与发送回报或事件中的 message_id 对应

        返回值：
        - 返回“撤回请求已发送”；协议接口不提供成功确认
        """
        await ctx.actions.del_msg(message_id)
        return f"撤回请求已发送：message_id={message_id}"

    @tool(group="qq", sub_visible=False, preserve=True)
    async def get_msg(self, ctx: ToolContext, message_id: int) -> Any:
        """获取消息详情（含发送者、时间、消息段），可用于查看被提及的未收到消息。

        - message_id: 目标消息 id

        返回值：
        - 成功时返回“获取消息成功”和协议端返回的消息详情
        - 上游明确失败时返回失败原因
        """
        ret = await ctx.actions.get_msg(message_id)
        if not _ret_succeeded(ret):
            return _ret_failure("获取消息", ret)
        detail = json.dumps(ret.raw.get("data"), ensure_ascii=False, default=str)
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
        echo = await ctx.actions.custom.send_like(user_id=user_id, times=times)
        ret = await _custom_ret(echo)
        if not _ret_succeeded(ret):
            return _ret_failure("点赞", ret)

        return f"点赞请求已发送：user_id={user_id}，times={times}"
