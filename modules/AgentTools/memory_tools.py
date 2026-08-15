"""记忆/状态类工具:历史总结、任务列表、角色设定(均经 ToolContext.runtime 操作 Agent 核心)。"""

from modules.AgentTools.registry import AgentToolBase, ToolContext, tool


class MemoryTools(AgentToolBase):
    @tool(perm="bot_owner", scenes=("private", "system"), group="memory")
    async def clear(self, ctx: ToolContext, content: str) -> str:
        """用总结性的信息代替完整聊天历史"""
        return await ctx.runtime.clear_history(content)

    @tool(group="memory")
    async def task_add(self, ctx: ToolContext, content: str) -> str:
        """向任务列表中添加任务，会返回任务编号"""
        return await ctx.runtime.task_add(content)

    @tool(group="memory")
    async def task_remove(self, ctx: ToolContext, index: int) -> str:
        """从任务列表中删除任务，需要任务编号"""
        return await ctx.runtime.task_remove(index)

    @tool(group="memory")
    async def task_list(self, ctx: ToolContext) -> str:
        """查看当前的任务列表"""
        return await ctx.runtime.task_list()

    @tool(group="memory")
    async def mem_add(self, ctx: ToolContext, content: str) -> str:
        """向长期记忆添加一条(如用户偏好、重要约定、值得记住的事实),自动向量化,重复内容自动去重。注意使用准确客观的语言"""
        return await ctx.runtime.mem_add(content)

    @tool(group="memory")
    async def mem_query(self, ctx: ToolContext, query: str, top_k: int = 5) -> str:
        """语义检索长期记忆,返回相关条目(会忽略拼写差异,如问"饮料"能查到"奶茶")。注意使用准确客观的语言"""
        return await ctx.runtime.mem_query(query, top_k)

    @tool(group="memory")
    async def mem_list(self, ctx: ToolContext, limit: int = 20) -> str:
        """列出最近的长期记忆条目"""
        return await ctx.runtime.mem_list(limit)

    @tool(group="memory")
    async def mem_del(self, ctx: ToolContext, mem_id: int) -> str:
        """删除指定 id 的长期记忆"""
        return await ctx.runtime.mem_delete(mem_id)
