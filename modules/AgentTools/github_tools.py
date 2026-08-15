"""GitHub API 工具集:查询仓库/issue/文件/用户等信息(只读)。

- 使用 GitHub REST API(https://api.github.com),可选 token:config.others["github_token"]
- 无 token 时受公共限流(60 次/小时/IP)
- 所有工具只读,不涉及写操作
"""

import base64
from typing import Any

import httpx
from hyperot import configurator

from modules.AgentTools.registry import AgentToolBase, ToolContext, tool

config = configurator.BotConfig.get("hyper-bot")

API = "https://api.github.com"
TIMEOUT = 10.0
MAX_TEXT = 2000  # 单个文本字段截断长度
MAX_OUTPUT = 4000  # 总输出截断长度


async def _gh_get(path: str, params: dict[str, Any] | None = None) -> tuple[int, Any]:
    """请求 GitHub API,返回 (状态码, JSON 数据或错误信息)。"""
    headers = {"User-Agent": "HypeR-Bot-Agent/1.0", "Accept": "application/vnd.github+json"}
    token = config.others.get("github_token")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(API + path, params=params, headers=headers)
        if resp.status_code != 200:
            if resp.status_code == 404:
                return 404, "资源不存在"
            if resp.status_code in (403, 429):
                return resp.status_code, "GitHub API 限流或权限不足(403/429)"
            return resp.status_code, f"请求失败: HTTP {resp.status_code}"
        return 200, resp.json()
    except Exception as e:
        return 0, f"请求异常: {e}"


def _clip(text: str, limit: int = MAX_TEXT) -> str:
    text = (text or "").strip()
    if len(text) > limit:
        return text[:limit] + f"...(已截断,共 {len(text)} 字符)"
    return text


def _out(text: str) -> str:
    if len(text) > MAX_OUTPUT:
        return text[:MAX_OUTPUT] + "\n...(输出过长,已截断)"
    return text


class GithubTools(AgentToolBase):
    @tool(group="github")
    async def gh_repo(self, ctx: ToolContext, repo: str) -> str:
        """查询 GitHub 仓库信息(描述、star/fork、语言、license、更新时间等)，repo 格式为 owner/repo"""
        code, data = await _gh_get(f"/repos/{repo}")
        if code != 200:
            return f"[{code}] {data}"
        license_name = (data.get("license") or {}).get("spdx_id") or "无"
        return _out(
            f"仓库: {data.get('full_name')}\n"
            f"描述: {data.get('description') or '(无)'}\n"
            f"⭐ {data.get('stargazers_count')} | 🍴 {data.get('forks_count')} | 👀 {data.get('watchers_count')}\n"
            f"语言: {data.get('language') or '未知'} | License: {license_name}\n"
            f"主页: {data.get('homepage') or '(无)'}\n"
            f"创建: {data.get('created_at')} | 最近更新: {data.get('pushed_at')}\n"
            f"默认分支: {data.get('default_branch')} | 归档: {data.get('archived')}"
        )

    @tool(group="github")
    async def gh_search_repos(self, ctx: ToolContext, query: str) -> str:
        """搜索 GitHub 仓库，返回前 5 条结果(全名/star/语言/描述)"""
        code, data = await _gh_get("/search/repositories", {"q": query, "per_page": 5})
        if code != 200:
            return f"[{code}] {data}"
        items = data.get("items", [])
        if not items:
            return "未找到相关仓库"
        lines = []
        for i in items:
            desc = _clip(i.get("description") or "(无描述)", 120)
            lines.append(
                f"⭐{i.get('stargazers_count')} {i.get('full_name')} [{i.get('language') or '未知'}]\n  {desc}"
            )
        return _out("\n\n".join(lines))

    @tool(group="github")
    async def gh_issue(self, ctx: ToolContext, repo: str, number: int) -> str:
        """查询 GitHub issue/PR 详情(标题、状态、作者、正文)，repo 为 owner/repo，number 为编号"""
        code, data = await _gh_get(f"/repos/{repo}/issues/{number}")
        if code != 200:
            return f"[{code}] {data}"
        kind = "PR" if "pull_request" in data else "Issue"
        labels = ", ".join(t.get("name", "") for t in data.get("labels", [])) or "(无)"
        return _out(
            f"#{data.get('number')} {data.get('title')} [{kind}]\n"
            f"状态: {data.get('state')} | 作者: {(data.get('user') or {}).get('login')} | 创建: {data.get('created_at')}\n"
            f"评论数: {data.get('comments')} | 标签: {labels}\n"
            f"---\n{_clip(data.get('body') or '(无正文)')}"
        )

    @tool(group="github")
    async def gh_read_file(self, ctx: ToolContext, repo: str, path: str) -> str:
        """读取 GitHub 仓库内文件内容(默认分支)，repo 为 owner/repo，path 为仓库内路径"""
        code, data = await _gh_get(f"/repos/{repo}/contents/{path}")
        if code != 200:
            return f"[{code}] {data}"
        try:
            content = base64.b64decode(data.get("content", "")).decode("utf-8", errors="replace")
        except Exception as e:
            return f"文件解码失败: {e}"
        return _out(f"文件: {data.get('path')}({data.get('size')} 字节)\n---\n{_clip(content)}")

    @tool(group="github")
    async def gh_releases(self, ctx: ToolContext, repo: str) -> str:
        """查询 GitHub 仓库最新 release(tag/名称/时间/正文)，repo 为 owner/repo"""
        code, data = await _gh_get("/repos/" + repo + "/releases", {"per_page": 3})
        if code != 200:
            return f"[{code}] {data}"
        if not data:
            return "该仓库暂无 release"
        lines = []
        for r in data:
            lines.append(
                f"{r.get('tag_name')} {r.get('name') or ''}\n"
                f"发布: {r.get('published_at')} | 作者: {(r.get('author') or {}).get('login')}\n"
                f"{_clip(r.get('body') or '(无正文)', 500)}"
            )
        return _out("\n\n".join(lines))

    @tool(group="github")
    async def gh_user(self, ctx: ToolContext, username: str) -> str:
        """查询 GitHub 用户信息(名字、bio、粉丝/关注、仓库数、位置)"""
        code, data = await _gh_get(f"/users/{username}")
        if code != 200:
            return f"[{code}] {data}"
        return _out(
            f"用户: {data.get('login')}({data.get('name') or '未设置姓名'})\n"
            f"bio: {data.get('bio') or '(无)'}\n"
            f"粉丝 {data.get('followers')} | 关注 {data.get('following')} | 公开仓库 {data.get('public_repos')}\n"
            f"位置: {data.get('location') or '未知'} | 主页: {data.get('blog') or '(无)'}\n"
            f"加入: {data.get('created_at')}"
        )
