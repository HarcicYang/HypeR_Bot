"""消息类工具:发消息、撤回、查消息、合并转发长文本。"""

import asyncio
import math
from typing import Any

from hyperot import common, segments

from modules.AgentTools.registry import AgentToolBase, SegmentsArg, ToolContext, tool

# 普通发送的最大序列化长度;超过则拒绝,强制使用 collected_send
MAX_TEXT_LEN = 120


def _check_len(msg: common.Message) -> str | None:
    """消息序列化后 str() 长度超过 MAX_TEXT_LEN 时返回错误信息(强制改用合并转发)。"""
    if len(str(msg)) > MAX_TEXT_LEN:
        return f"消息过长(序列化后 {len(str(msg))} 字符,上限 {MAX_TEXT_LEN})，请改用 collected_send 以合并转发形式发送"
    return None


class MessageTools(AgentToolBase):
    @tool(group="qq", sub_visible=False)
    async def send_group_msg(self, ctx: ToolContext, group_id: int, message: SegmentsArg) -> Any:
        """向指定群发送消息，返回 message_id（可用于引用、撤回）。

        - group_id: 目标群号，与事件中的 group_id 对应
        - message: 消息段数组（text/at/reply/image）
        - 消息序列化后超过 120 字符会被拒绝，长文本必须改用 collected_send
        """
        new_mess = await ctx.create_msg(message)
        if err := _check_len(new_mess):
            return err
        await asyncio.sleep(math.log(len(str(new_mess)) + 3))
        return (await ctx.actions.send_msg(message=new_mess, group_id=group_id)).raw

    @tool(group="qq", sub_visible=False)
    async def send_private_msg(self, ctx: ToolContext, user_id: int, message: SegmentsArg) -> Any:
        """向指定用户私聊发送消息（需有对方好友），返回 message_id。

        - user_id: 目标用户 QQ 号
        - message: 消息段数组（text/at/reply/image）
        - 消息序列化后超过 120 字符会被拒绝，长文本必须改用 collected_send
        """
        new_mess = await ctx.create_msg(message)
        if err := _check_len(new_mess):
            return err
        return (await ctx.actions.send_msg(message=new_mess, user_id=user_id)).raw

    @tool(group="qq", sub_visible=False)
    async def collected_send(
        self, ctx: ToolContext, message: SegmentsArg, group_id: int | None = None, user_id: int | None = None
    ) -> Any:
        """以合并转发（聊天记录卡片）形式发送消息，避免长文本刷屏。

        - message: 消息段数组，整条消息作为一个节点（不拆分，保留 text/at/reply 等全部段）
        - group_id / user_id: 目标群号或用户 QQ 号，必须且只能提供一个
        - 消息文本较长（超过 120 字符）时使用本工具
        """
        if (group_id is None) == (user_id is None):
            return "调用不合法：group_id 与 user_id 必须且只能提供一个"
        new_mess = await ctx.create_msg(message)
        if len(new_mess) == 0:
            return "调用不合法：消息内容为空"
        nodes = [
            segments.CustomNode(
                user_id=str(ctx.self_id or ctx.principal_id or 0), nick_name="", content=new_mess
            ).to_json()
        ]
        fwd = common.Message(segments.Forward(content=nodes))
        if group_id is not None:
            return (await ctx.actions.send_msg(message=fwd, group_id=group_id)).raw
        return (await ctx.actions.send_msg(message=fwd, user_id=user_id)).raw

    @tool(group="qq", sub_visible=False)
    async def del_msg(self, ctx: ToolContext, message_id: int) -> str:
        """撤回消息（只可撤回自己发送的）。

        - message_id: 目标消息 id，与发送回报或事件中的 message_id 对应
        """
        await ctx.actions.del_msg(message_id)
        return "(无返回)"

    @tool(group="qq", sub_visible=False)
    async def get_msg(self, ctx: ToolContext, message_id: int) -> Any:
        """获取消息详情（含发送者、时间、消息段），可用于查看被提及的未收到消息。

        - message_id: 目标消息 id
        """
        return (await ctx.actions.get_msg(message_id)).raw

    @tool(group="qq", sub_visible=False)
    async def resolve_forward(self, ctx: ToolContext, forward_id: str) -> str:
        """解析合并转发消息，返回每条消息的发送者昵称与内容（段 JSON）。

        - forward_id: 合并转发 id，来自事件中 forward 段的 data.id
        """
        return await ctx.runtime.resolve_forward(forward_id)
