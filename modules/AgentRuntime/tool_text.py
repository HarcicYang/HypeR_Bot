"""Tool descriptions and command duration helpers."""

import re
import time
from typing import Any

from modules.AgentTools.registry import ToolRegistry


def format_remain(secs: float) -> str:
    secs = max(0, int(secs))
    if secs < 60:
        return f"{secs}秒"
    if secs < 3600:
        return f"{secs // 60}分{secs % 60:02d}秒"
    if secs < 86400:
        return f"{secs // 3600}小时{(secs % 3600) // 60:02d}分"
    return f"{secs // 86400}天{(secs % 86400) // 3600}小时"


def build_tools_section(role: str = "main") -> str:
    lines: list[str] = []
    for tool in ToolRegistry.schema(role=role):
        function = tool["function"]
        name = function["name"]
        params = function.get("parameters", {}).get("properties", {})
        args = ", ".join(params.keys())
        until = ToolRegistry.disabled_until(name)
        if until is None:
            mark = ""
        elif until == ToolRegistry.PERMANENT:
            mark = "[禁用中,待手动启用] "
        else:
            mark = f"[禁用中,剩{format_remain(until - time.time())}] "
        lines.append(f"- {mark}`{name}({args})` {function['description']}")
    return "\n".join(lines)


def parse_duration_minutes(text: str) -> float | None:
    text = text.strip().lower()
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(s|sec|秒|m|min|分钟|h|hour|小时|d|day|天)?", text)
    if not match:
        raise ValueError("时长格式错误")
    value = float(match.group(1))
    unit = match.group(2) or "m"
    if unit in ("s", "sec", "秒"):
        minutes = value / 60.0
    elif unit in ("m", "min", "分钟"):
        minutes = value
    elif unit in ("h", "hour", "小时"):
        minutes = value * 60.0
    elif unit in ("d", "day", "天"):
        minutes = value * 1440.0
    else:
        raise ValueError("时长单位错误")
    if minutes <= 0:
        raise ValueError("时长必须大于0")
    return minutes


def func_status_text() -> str:
    lines: list[str] = ["Agent 工具:"]
    by_group: dict[str, list[Any]] = {}
    for registration in ToolRegistry.registrations():
        by_group.setdefault(registration.group, []).append(registration)
    for group in sorted(by_group):
        lines.append(f"[{group}]")
        for registration in by_group[group]:
            until = ToolRegistry.disabled_until(registration.name)
            if until is None:
                status = "启用"
            elif until == ToolRegistry.PERMANENT:
                status = "禁用(手动启用前有效)"
            else:
                status = f"禁用(剩{format_remain(until - time.time())})"
            desc = (registration.desc or "").strip().splitlines()
            first = desc[0] if desc else ""
            if len(first) > 20:
                first = first[:20] + "…"
            lines.append(f"  {registration.name} | {status} | {first}")
    return "\n".join(lines)
