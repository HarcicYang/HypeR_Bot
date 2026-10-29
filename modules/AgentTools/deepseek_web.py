"""DeepSeek 官方 Search / Fetch API 客户端。

文档:
- https://api-docs.deepseek.com/guides/search
- https://api-docs.deepseek.com/api/search
- https://api-docs.deepseek.com/api/fetch
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any
from urllib.parse import urlparse

import httpx
from hyperot import configurator

from modules.AgentTools.registry import ToolContext

config = configurator.BotConfig.get("hyper-bot")
_logger = logging.getLogger(__name__)

DEEPSEEK_API_BASE = "https://api.deepseek.com"
DEEPSEEK_SEARCH_PATH = "/v1/tools/search"
DEEPSEEK_FETCH_PATH = "/v1/tools/fetch"
DEEPSEEK_SEARCH_TIMEOUT = 20.0
DEEPSEEK_FETCH_TIMEOUT = 40.0
DEEPSEEK_MAX_ATTEMPTS = 2
DEEPSEEK_RETRY_DELAY = 0.5
DEEPSEEK_MAX_RETRY_DELAY = 2.0
_RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504}


class DeepSeekWebUnavailable(RuntimeError):
    """DeepSeek Web API 当前无法提供可用结果。"""


class DeepSeekNotConfigured(DeepSeekWebUnavailable):
    """未配置可用的 DeepSeek API key。"""


def _clean_api_key(value: Any) -> str:
    key = str(value or "").strip()
    if key.lower().startswith("bearer "):
        key = key[7:].strip()
    return key


def _active_profile_api_key(ctx: ToolContext) -> str:
    runtime = getattr(ctx, "runtime", None)
    manager = getattr(runtime, "api_manager", None)
    if manager is None:
        return ""
    try:
        profile = manager.get_profile(manager.active_profile)
    except Exception:
        return ""
    parsed = urlparse(profile.base_url)
    if parsed.hostname != "api.deepseek.com":
        return ""
    return _clean_api_key(profile.api_key)


def _resolve_api_key(ctx: ToolContext) -> str:
    """按显式配置、环境变量、当前 DeepSeek profile 的顺序解析 API key。"""
    configured = _clean_api_key(config.others.get("deepseek_api_key"))
    if configured:
        return configured
    environment = _clean_api_key(os.environ.get("DEEPSEEK_API_KEY"))
    if environment:
        return environment
    return _active_profile_api_key(ctx)


def _error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        payload = None
    message = ""
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = str(error.get("message") or "")
    if not message:
        message = (response.text or "").strip()
    message = " ".join(message.split())
    return message[:300]


def _retry_delay(response: httpx.Response | None, attempt: int) -> float:
    if response is not None:
        raw = response.headers.get("retry-after", "").strip()
        try:
            requested = float(raw)
        except ValueError:
            requested = 0.0
        if requested > 0:
            return min(requested, DEEPSEEK_MAX_RETRY_DELAY)
    return min(DEEPSEEK_RETRY_DELAY * (2**attempt), DEEPSEEK_MAX_RETRY_DELAY)


async def _post(ctx: ToolContext, path: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
    api_key = _resolve_api_key(ctx)
    if not api_key:
        raise DeepSeekNotConfigured(
            "未配置 DeepSeek API key（config.others.deepseek_api_key / DEEPSEEK_API_KEY / DeepSeek profile）"
        )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "HypeR-Bot-Agent/1.0",
    }
    endpoint = DEEPSEEK_API_BASE + path
    last_error = ""
    for attempt in range(DEEPSEEK_MAX_ATTEMPTS):
        response: httpx.Response | None = None
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(endpoint, headers=headers, json=payload)
            if 200 <= response.status_code < 300:
                try:
                    data = response.json()
                except ValueError as exc:
                    raise DeepSeekWebUnavailable("DeepSeek 返回了无效 JSON") from exc
                if not isinstance(data, dict):
                    raise DeepSeekWebUnavailable("DeepSeek 返回了非对象 JSON")
                return data

            detail = _error_message(response)
            last_error = f"HTTP {response.status_code}" + (f": {detail}" if detail else "")
            if response.status_code not in _RETRYABLE_STATUS or attempt + 1 >= DEEPSEEK_MAX_ATTEMPTS:
                raise DeepSeekWebUnavailable(last_error)
        except httpx.HTTPError as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            if attempt + 1 >= DEEPSEEK_MAX_ATTEMPTS:
                raise DeepSeekWebUnavailable(last_error) from exc
        await asyncio.sleep(_retry_delay(response, attempt))

    raise DeepSeekWebUnavailable(last_error or "未知错误")


async def search(ctx: ToolContext, query: str, count: int) -> list[dict[str, Any]]:
    """调用 DeepSeek Search API，空结果是合法成功响应。"""
    data = await _post(
        ctx,
        DEEPSEEK_SEARCH_PATH,
        {"query": query, "count": count, "need_content": False},
        DEEPSEEK_SEARCH_TIMEOUT,
    )
    results = data.get("results")
    if not isinstance(results, list):
        raise DeepSeekWebUnavailable("DeepSeek Search 响应缺少 results 数组")
    if not results:
        return []

    normalized: list[dict[str, Any]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        if not title and not url:
            continue
        normalized.append(item)
    if not normalized:
        raise DeepSeekWebUnavailable("DeepSeek Search 响应中没有有效结果")
    return normalized


async def fetch(ctx: ToolContext, url: str) -> tuple[str, str]:
    """调用 DeepSeek Fetch API，返回 (标题, Markdown 正文)。"""
    data = await _post(ctx, DEEPSEEK_FETCH_PATH, {"url": url}, DEEPSEEK_FETCH_TIMEOUT)
    raw_title = data.get("title")
    raw_content = data.get("content")
    title = raw_title.strip() if isinstance(raw_title, str) else ""
    content = raw_content.strip() if isinstance(raw_content, str) else ""
    if not content:
        raise DeepSeekWebUnavailable("DeepSeek Fetch 未返回页面正文")
    return title, content


def log_unavailable(tool: str, exc: Exception) -> None:
    """记录默认链路不可用；缺少配置属于预期降级，不刷 warning。"""
    level = logging.DEBUG if isinstance(exc, DeepSeekNotConfigured) else logging.WARNING
    _logger.log(level, "%s 的 DeepSeek 默认链路不可用，执行本地回退: %s", tool, exc)
