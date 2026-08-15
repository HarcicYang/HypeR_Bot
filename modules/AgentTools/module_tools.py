"""模块调用工具:让 Agent 发现并调用 bot 的其他功能模块。

- list_modules:模块目录(名称/简介/触发方式)
- run_module:以合成事件驱动模块 handle(),发送被捕获为段 JSON 移交 Agent
- get_module_source:查看模块源码,帮助理解触发逻辑
"""

from modules.AgentTools.registry import AgentToolBase, ToolContext, tool


class ModuleTools(AgentToolBase):
    @tool(group="general")
    async def list_modules(self, ctx: ToolContext) -> str:
        """列出可调用的功能模块及触发方式(命令/触发词,来自各模块帮助)"""
        return await ctx.runtime.list_modules()

    @tool(group="general")
    async def run_module(self, ctx: ToolContext, module: str, command: str) -> str:
        """调用功能模块:command 为完整消息文本(如 ".q xxx" 或触发词"透我");
        模块想发送的内容会被捕获为段 JSON 返回,由你决定是否转发"""
        return await ctx.runtime.run_module(ctx, module, command)

    @tool(group="general")
    async def get_module_source(self, ctx: ToolContext, module: str) -> str:
        """查看模块源码(handle 与命令逻辑),了解其触发方式;调用模块失败时使用"""
        return await ctx.runtime.get_module_source(module)
