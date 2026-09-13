"""Tools for searching and paging complete content saved by other tools."""

import asyncio
import json
from typing import Any

from modules.AgentRuntime.content_store import ContentStore
from modules.AgentTools.registry import AgentToolBase, ToolContext, tool


def _store_for(ctx: ToolContext) -> ContentStore:
    runtime = ctx.runtime
    session_key = getattr(runtime, "session_key", None)
    scope = getattr(session_key, "value", None) or getattr(runtime, "name", None) or "default"
    return ContentStore(str(scope))


def _dump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


class ContentTools(AgentToolBase):
    @tool(group="content", system_visible=True)
    async def content_list(self, ctx: ToolContext, limit: int = 20) -> str:
        """列出当前上下文最近保存的完整内容及其 content_id、来源、标题和长度。"""
        items = await asyncio.to_thread(_store_for(ctx).list, limit)
        return _dump({"items": items})

    @tool(group="content", system_visible=True)
    async def content_info(self, ctx: ToolContext, content_id: str) -> str:
        """查看完整内容的元数据；content_id 来自大型工具结果的保存提示。"""
        info = await asyncio.to_thread(_store_for(ctx).info, content_id)
        return _dump(info if info is not None else {"error": f"内容 {content_id} 不存在或已清理"})

    @tool(group="content", system_visible=True)
    async def content_search(
        self,
        ctx: ToolContext,
        content_id: str,
        query: str,
        max_results: int = 5,
        context_lines: int = 2,
    ) -> str:
        """在完整内容中搜索关键词，返回命中片段及精确字符范围。

        - content_id: content_list 或大型工具结果提示中的内容 id
        - query: 搜索词
        - max_results: 最多返回片段数，1-20
        - context_lines: 每个命中位置附带的上下文行数，0-10
        """
        result = await asyncio.to_thread(
            _store_for(ctx).search,
            content_id,
            query,
            max_results,
            context_lines,
        )
        return _dump(result)

    @tool(group="content", system_visible=True)
    async def content_read(self, ctx: ToolContext, content_id: str, offset: int = 0, limit: int = 4000) -> str:
        """按字符位置读取完整内容；返回 next_offset，继续读取时把它作为下一次 offset。

        - content_id: content_list 或大型工具结果提示中的内容 id
        - offset: 起始字符位置；负数表示从末尾往前计数
        - limit: 本次读取字符数，最大 12000
        """
        result = await asyncio.to_thread(_store_for(ctx).read, content_id, offset, limit)
        return _dump(result)
