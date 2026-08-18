"""管理/状态类工具:登录/版本/运行状态、群名片、表情回应。"""

from typing import Any

from modules.AgentTools.registry import AgentToolBase, ToolContext, tool


class AdminTools(AgentToolBase):
    @tool(scenes=("group", "private", "system"), group="admin", sub_visible=False)
    async def get_status(self, ctx: ToolContext) -> Any:
        """查询 Bot 当前状态"""
        return (await ctx.actions.get_status()).raw

    @tool(scenes=("group", "private", "system"), group="admin", sub_visible=False)
    async def get_login_info(self, ctx: ToolContext) -> Any:
        """查询 Bot 登录账号信息"""
        return (await ctx.actions.get_login_info()).raw

    @tool(scenes=("group", "private", "system"), group="admin", sub_visible=False)
    async def get_version_info(self, ctx: ToolContext) -> Any:
        """查询 Bot 版本与协议实现信息"""
        return (await ctx.actions.get_version_info()).raw

    @tool(perm="bot_owner", scenes=("group",), group="admin", sub_visible=False)
    async def set_group_card(self, ctx: ToolContext, group_id: int, user_id: int, card: str) -> str:
        """设置指定群成员的群名片。

        - group_id: 目标群号
        - user_id: 目标用户 QQ 号
        - card: 新的群名片内容(留空表示清除)
        """
        if len(card) > 32:
            return "群名片过长(最多 32 字符)"
        echo = await ctx.actions.custom.set_group_card(group_id=group_id, user_id=user_id, card=card)
        return f"已设置群 {group_id} 中用户 {user_id} 的名片(echo={echo})"
