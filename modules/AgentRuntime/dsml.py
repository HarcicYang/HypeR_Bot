"""Repair tool calls embedded as DSML/XML assistant text."""

import contextlib
import html
import json
import re
import uuid
from typing import Any

from hyperot import configurator, hyperogger

config = configurator.BotConfig.get("hyper-bot")
logger = hyperogger.Logger()
logger.set_level(config.log_level)

_DSML_BAR = r"(?:\uff5c{1,2}|\|{1,2})"
_DSML_PREFIX = rf"(?:{_DSML_BAR}DSML{_DSML_BAR})?"
_TOOL_BLOCK_RE = re.compile(
    rf"<{_DSML_PREFIX}\s*(?P<open>function_calls|tool_calls)\s*>(?P<body>.*?)</{_DSML_PREFIX}\s*(?P<close>function_calls|tool_calls)\s*>",
    re.IGNORECASE | re.DOTALL,
)
_INVOKE_RE = re.compile(
    rf"<{_DSML_PREFIX}\s*invoke\b(?P<attrs>[^>]*)>(?P<body>.*?)</{_DSML_PREFIX}\s*invoke\s*>",
    re.IGNORECASE | re.DOTALL,
)
_PARAM_RE = re.compile(
    rf"<{_DSML_PREFIX}\s*parameter\b(?P<attrs>[^>]*)>(?P<value>.*?)</{_DSML_PREFIX}\s*parameter\s*>",
    re.IGNORECASE | re.DOTALL,
)
_ATTR_RE = re.compile(r"""(?P<name>[A-Za-z_][A-Za-z0-9_-]*)\s*=\s*["'](?P<value>[^"']*)["']""")


def _tag_attrs(attrs: str) -> dict[str, str]:
    return {match.group("name"): html.unescape(match.group("value")) for match in _ATTR_RE.finditer(attrs)}


def parse_embedded_tool_calls(text: str) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    tool_calls: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    for block in _TOOL_BLOCK_RE.finditer(text):
        for invocation in _INVOKE_RE.finditer(block.group("body")):
            name = _tag_attrs(invocation.group("attrs") or "").get("name", "").strip()
            if not name:
                continue
            params: dict[str, Any] = {}
            for parameter in _PARAM_RE.finditer(invocation.group("body")):
                parameter_name = _tag_attrs(parameter.group("attrs") or "").get("name", "").strip()
                if not parameter_name:
                    continue
                value: Any = html.unescape(parameter.group("value")).strip()
                with contextlib.suppress(json.JSONDecodeError):
                    value = json.loads(value)
                params[parameter_name] = value
            call_id = f"call_{uuid.uuid4().hex}"
            arguments = json.dumps(params, ensure_ascii=False)
            tool_calls.append({"id": call_id, "type": "function", "function": {"name": name, "arguments": arguments}})
            actions.append({"kind": "function", "call_id": call_id, "name": name, "arguments": arguments})
    if tool_calls:
        logger.warning(f"已将 content 中的 {len(tool_calls)} 个 DSML/XML 伪工具调用解析为 function_call")
    cleaned = _TOOL_BLOCK_RE.sub("", text)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned or "{}", tool_calls, actions
