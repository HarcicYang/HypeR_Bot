import asyncio
from typing import Any

from modules.AgentTools import deepseek_web
from modules.AgentTools.registry import AgentToolBase, ToolContext, tool


def _do_search(
    query: str,
    region: str,
    safesearch: str,
    timelimit: str,
    max_results: int,
    backend: str,
) -> list[dict[str, Any]]:
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
        """联网搜索:默认使用 DeepSeek 官方 Search API,不可用时回退到多引擎搜索。

        - query: 搜索关键词
        - max_results: 返回条数(默认 5,上限 10)
        - region: 回退搜索的结果地区,如 cn-zh / us-en
        - timelimit: 回退搜索的时间过滤 d/w/m/y,留空为不限
        - backend: 回退搜索的指定引擎(duckduckgo/google/brave/mojeek/startpage/wikipedia),auto 为自动选
        """
        max_results = max(1, min(max_results, 10))
        try:
            results = await deepseek_web.search(ctx, query, max_results)
        except deepseek_web.DeepSeekWebUnavailable as exc:
            deepseek_web.log_unavailable("web_search", exc)
            deepseek_failure = f"{type(exc).__name__}: {exc}"
        else:
            if not results:
                return f"没有找到与「{query}」相关的结果"
            lines: list[str] = []
            for i, result in enumerate(results, 1):
                title = str(result.get("title") or "").strip()
                url = str(result.get("url") or "").strip()
                summary = str(result.get("summary") or result.get("snippet") or "").strip()
                lines.append(f"{i}. {title}\n   {url}\n   {summary}")
            return "\n".join(lines)

        try:
            results = await asyncio.to_thread(_do_search, query, region, "moderate", timelimit, max_results, backend)
        except Exception as exc:
            return f"搜索失败: DeepSeek Search 不可用（{deepseek_failure}）；回退搜索失败: {type(exc).__name__}: {exc}"

        if not results:
            return f"没有找到与「{query}」相关的结果"

        lines: list[str] = []
        for i, r in enumerate(results, 1):
            title = (r.get("title") or "").strip()
            href = (r.get("href") or r.get("url") or "").strip()
            body = (r.get("body") or r.get("description") or "").strip()
            lines.append(f"{i}. {title}\n   {href}\n   {body}")
        return "\n".join(lines)
