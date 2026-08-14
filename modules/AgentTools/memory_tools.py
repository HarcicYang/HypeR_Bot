"""记忆/状态类工具:历史总结、任务列表、角色设定(均经 ToolContext.runtime 操作 Agent 核心)。"""

from modules.AgentTools.registry import AgentToolBase, ToolContext, tool


class MemoryTools(AgentToolBase):
    @tool(perm="bot_owner", scenes=("private", "system"))
    async def clear(self, ctx: ToolContext, content: str) -> str:
        """用总结性的信息代替完整聊天历史"""
        return await ctx.runtime.clear_history(content)

    @tool()
    async def task_add(self, ctx: ToolContext, content: str) -> str:
        """向任务列表中添加任务，会返回任务编号"""
        return await ctx.runtime.task_add(content)

    @tool()
    async def task_remove(self, ctx: ToolContext, index: int) -> str:
        """从任务列表中删除任务，需要任务编号"""
        return await ctx.runtime.task_remove(index)

    @tool()
    async def task_list(self, ctx: ToolContext) -> str:
        """查看当前的任务列表"""
        return await ctx.runtime.task_list()

    @tool(perm="bot_owner", scenes=("private",))
    async def profile(self, ctx: ToolContext, prompt: str) -> str:
        """更改启用的角色设定，只允许主人调用"""
        return await ctx.runtime.set_profile(prompt)
