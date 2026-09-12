import asyncio
from typing import Any

from modules.AgentTools.registry import AgentToolBase, ToolContext, tool


def _do_search(query, region, safesearch, timelimit, max_results, backend):
    from ddgs import DDGS

    with DDGS() as ddgs:
        return ddgs.text(
            query,
            region=region,
            safesearch=safesearch,
            timelimit=timelimit or None,
            max_results=max_results,
            backend=backend,
        )


class SearchTools(AgentToolBase):
    @tool(scenes=("group", "private", "system"), group="search", sub_visible=True)
    async def web_search(
        self,
        ctx: ToolContext,
        query: str,
        max_results: int = 5,
        region: str = "cn-zh",
        timelimit: str = "",
        backend: str = "auto",
    ) -> Any:
        """联网搜索:聚合 DuckDuckGo/Bing/Google 等引擎的实时结果。

        - query: 搜索关键词
        - max_results: 返回条数(默认 5,上限 10)
        - region: 结果地区,如 cn-zh / us-en
        - timelimit: 时间过滤 d/w/m/y,留空为不限
        - backend: 指定引擎(duckduckgo/google/brave/mojeek/startpage/wikipedia),auto 为自动选
        """
        max_results = max(1, min(int(max_results), 10))
        try:
            results = await asyncio.to_thread(
                _do_search, query, region, "moderate", timelimit, max_results, backend
            )
        except Exception as exc:
            return f"搜索失败: {type(exc).__name__}: {exc}"

        if not results:
            return f"没有找到与「{query}」相关的结果"

        lines = []
        for i, r in enumerate(results, 1):
            title = (r.get("title") or "").strip()
            href = (r.get("href") or r.get("url") or "").strip()
            body = (r.get("body") or r.get("description") or "").strip()
            lines.append(f"{i}. {title}\n   {href}\n   {body}")
        return "\n".join(lines)