"""Main/System 上下文查询、通信与管理工具。"""

from modules.AgentTools.registry import AgentToolBase, ToolContext, tool


class ContextTools(AgentToolBase):
    @tool(group="context", sub_visible=False, system_visible=True)
    async def context_list(self, ctx: ToolContext) -> str:
        """列出全部 Main 会话上下文及其类型、轮次数、更新时间。"""
        return await ctx.runtime.context_list()

    @tool(group="context", sub_visible=False, system_visible=True)
    async def context_status(self, ctx: ToolContext, target: str) -> str:
        """查看指定 Main 上下文状态。target 格式为 group:<群号> 或 private:<QQ号>。"""
        return await ctx.runtime.context_status(target)

    @tool(group="context", sub_visible=False, system_visible=True)
    async def context_read(
        self,
        ctx: ToolContext,
        target: str,
        count: int = 5,
        anchor: int | None = None,
        direction: str = "backward",
    ) -> str:
        """读取指定 Main 上下文的原始会话轮次。

        - target: group:<群号> 或 private:<QQ号>
        - count: 读取轮数，1-50，默认 5
        - anchor: 轮次序号；不填表示从最后一轮开始
        - direction: backward 向前读取，forward 向后读取
        """
        return await ctx.runtime.context_read(target, count, anchor, direction)

    @tool(group="context", sub_visible=False, system_visible=True)
    async def context_send(self, ctx: ToolContext, target: str, content: str) -> str:
        """向另一个 Main 上下文投递消息；目标会话将在自己的独立历史中处理。"""
        return await ctx.runtime.context_send(target, content, "message")

    @tool(group="context", sub_visible=False, system_visible=True)
    async def context_request(self, ctx: ToolContext, target: str, content: str) -> str:
        """向另一个 Main 上下文发起协作请求，返回可供 context_reply 使用的 request_id。"""
        return await ctx.runtime.context_send(target, content, "request")

    @tool(group="context", sub_visible=False, system_visible=True)
    async def context_reply(self, ctx: ToolContext, target: str, request_id: str, content: str) -> str:
        """回复另一个 Main 上下文发来的协作请求。"""
        return await ctx.runtime.context_send(target, content, "reply", request_id)

    @tool(
        perm="bot_owner",
        scenes=("system",),
        group="context",
        main_visible=False,
        sub_visible=False,
        system_visible=True,
    )
    async def context_replace_summary(
        self,
        ctx: ToolContext,
        target: str,
        content: str,
        through_turn: int,
    ) -> str:
        """用摘要替换目标 Main 上下文截至 through_turn 的历史前缀，并保留之后的新轮次。"""
        return await ctx.runtime.context_replace_summary(target, content, through_turn)
