"""消息类工具:发消息、撤回、查消息、合并转发长文本。"""

import asyncio
import math
from typing import Any

from hyperot import common, segments

from modules.AgentTools.registry import AgentToolBase, SegmentsArg, ToolContext, tool


def _split_long_text(msg: common.Message) -> list[str]:
    """把消息文本拆成适合合并转发节点的短段(按行、超长再按字符切)。"""
    text = str(msg)
    parts: list[str] = []
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        while len(line) > 40:
            parts.append(line[:40])
            line = line[40:]
        parts.append(line)
    return parts


class MessageTools(AgentToolBase):
    @tool()
    async def send_group_msg(self, ctx: ToolContext, group_id: int, message: SegmentsArg) -> Any:
        """向指定的群组发送消息，会返回 message_id，可用于引用回复、撤回等操作"""
        new_mess = await ctx.create_msg(message)
        await asyncio.sleep(math.log(len(str(new_mess)) + 3))
        return (await ctx.actions.send_msg(message=new_mess, group_id=group_id)).raw

    @tool()
    async def send_private_msg(self, ctx: ToolContext, user_id: int, message: SegmentsArg) -> Any:
        """向指定的用户私聊发送消息（需要有对方的好友），会返回 message_id"""
        new_mess = await ctx.create_msg(message)
        return (await ctx.actions.send_msg(message=new_mess, user_id=user_id)).raw

    @tool()
    async def collected_send(
        self, ctx: ToolContext, message: SegmentsArg, group_id: int | None = None, user_id: int | None = None
    ) -> Any:
        """文本内容很长时使用：将消息以合并转发（聊天记录卡片）形式发送，避免长文本刷屏；group_id 与 user_id 必须且只能提供一个"""
        if (group_id is None) == (user_id is None):
            return "调用不合法：group_id 与 user_id 必须且只能提供一个"
        nodes = [
            segments.CustomNode(
                user_id=str(ctx.principal_id or 0), nick_name="", content=common.Message(segments.Text(part))
            ).to_json()
            for part in _split_long_text(await ctx.create_msg(message))
        ]
        if not nodes:
            return "调用不合法：消息内容为空"
        fwd = common.Message(segments.Forward(content=nodes))
        if group_id is not None:
            return (await ctx.actions.send_msg(message=fwd, group_id=group_id)).raw
        return (await ctx.actions.send_msg(message=fwd, user_id=user_id)).raw

    @tool()
    async def del_msg(self, ctx: ToolContext, message_id: int) -> str:
        """撤回消息，只可以撤回你自己发送的哦"""
        await ctx.actions.del_msg(message_id)
        return "(无返回)"

    @tool()
    async def get_msg(self, ctx: ToolContext, message_id: int) -> Any:
        """获取消息信息，这个消息可能是你没有收到但是被别人提及的消息"""
        return (await ctx.actions.get_msg(message_id)).raw
