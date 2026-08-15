"""SubAgent 工具:主 Agent 创建/销毁/管理后台 SubAgent(独立提示词,共享工具)。"""

from modules.AgentTools.registry import AgentToolBase, ToolContext, tool


class SubAgentTools(AgentToolBase):
    @tool(group="subagent")
    async def sub_create(self, ctx: ToolContext, name: str, prompt: str, scene_id: int, scene_type: str) -> str:
        """创建后台 SubAgent（上限 3 个）：指定名称、独立提示词与归属场景（scene_type 为 group 或 private，scene_id 为群号/QQ 号）。

        SubAgent 不监听 QQ 消息流，只处理你通过 sub_feed 显式投喂的任务；
        任务完成后用 sub_report 汇报，状态变化会自动通知你。
        """
        return await ctx.runtime.sub_create(name, prompt, scene_id, scene_type, ctx.perm_group)

    @tool(group="subagent")
    async def sub_destroy(self, ctx: ToolContext, sub_id: int) -> str:
        """销毁指定的 SubAgent，释放其占用的数量名额"""
        return await ctx.runtime.sub_destroy(sub_id)

    @tool(group="subagent")
    async def sub_list(self, ctx: ToolContext) -> str:
        """列出当前全部 SubAgent（id/名称/状态/订阅场景/数量上限）"""
        return await ctx.runtime.sub_list()

    @tool(group="subagent")
    async def sub_status(self, ctx: ToolContext, sub_id: int) -> str:
        """查询单个 SubAgent 的状态（订阅场景、权限、历史消息数等）"""
        return await ctx.runtime.sub_status(sub_id)

    @tool(release=True, group="subagent")
    async def sub_feed(self, ctx: ToolContext, sub_id: int, content: str) -> str:
        """向指定的 SubAgent 显式投喂一条消息，触发其后台处理；投喂后本轮处理结束，SubAgent 在后台独立运行，状态变化会自动通知"""
        return await ctx.runtime.sub_feed(sub_id, content, ctx.perm_group)

    @tool(group="subagent", main_visible=False)
    async def sub_report(self, ctx: ToolContext, content: str, need_response: bool = False) -> str:
        """向主 Agent 报告信息，主 Agent 将在下一轮处理时看到。

        - content: 报告内容（任务结果、进度、求助等）
        - need_response: **默认 false**。任务完成/进度/结果汇报一律用 false，报告完即可继续，不得挂起；
          仅当确实需要主 Agent 提供决策、授权或额外信息、且没有它就无法继续时，才设为 true 并明确提出需要回答的问题；
          同一时间只能有一个待回复报告
        """
        return await ctx.runtime.report(content, need_response)

    @tool(group="subagent", sub_visible=False)
    async def sub_reply(self, ctx: ToolContext, report_id: str, content: str) -> str:
        """回复 SubAgent 的 report（report_id 来自 subagent_status 事件中的报告）；仅主 Agent 使用，回复内容将送达等待中的 SubAgent"""
        return await ctx.runtime.sub_reply(report_id, content)
