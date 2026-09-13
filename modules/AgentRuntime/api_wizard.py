"""Interactive QQ wizard for creating and editing API profiles."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any, Literal

from .api_profiles import (
    ApiProfile,
    ApiProfileError,
    ApiProfileManager,
    normalize_api_mode,
    normalize_base_url,
    normalize_headers,
    normalize_model_name,
    redact_headers,
    validate_profile_name,
)

WIZARD_TIMEOUT = 600

_FIELD_ALIASES = {
    "url": "base_url",
    "base_url": "base_url",
    "key": "api_key",
    "api_key": "api_key",
    "md": "model",
    "model": "model",
    "mode": "api_mode",
    "api_mode": "api_mode",
    "reason": "reasoning_effort",
    "reasoning": "reasoning_effort",
    "reasoning_effort": "reasoning_effort",
    "web": "web_search",
    "web_search": "web_search",
    "multi": "native_multimodal",
    "multimodal": "native_multimodal",
    "native_multimodal": "native_multimodal",
    "hdr": "headers",
    "headers": "headers",
}
_EDITABLE_FIELDS = (
    "base_url",
    "api_key",
    "model",
    "api_mode",
    "reasoning_effort",
    "web_search",
    "native_multimodal",
    "headers",
)
_ADD_STEPS = (
    "__name__",
    "base_url",
    "api_key",
    "model",
    "api_mode",
    "reasoning_effort",
    "web_search",
    "native_multimodal",
    "headers",
    "__confirm__",
)
_OPTIONAL_FIELDS = {
    "base_url",
    "api_mode",
    "reasoning_effort",
    "web_search",
    "native_multimodal",
    "headers",
}


@dataclass(frozen=True)
class WizardReply:
    response: str


@dataclass
class WizardSession:
    uid: int
    kind: Literal["add", "set", "remove"]
    profile_name: str
    steps: list[str]
    index: int
    draft: dict[str, Any]
    original: ApiProfile | None = None
    edit_field: str | None = None
    updated_at: float = field(default_factory=time.monotonic)


def _strip_outer_quotes(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ("'", '"'):
        return text[1:-1]
    return text


def _parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in ("on", "true", "1", "yes", "y", "开", "开启", "是"):
        return True
    if normalized in ("off", "false", "0", "no", "n", "关", "关闭", "否"):
        return False
    raise ApiProfileError("请输入 on/off、true/false 或 1/0")


def _parse_headers(value: str) -> dict[str, str]:
    text = _strip_outer_quotes(value)
    if text.lower() == "skip":
        return {}
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ApiProfileError(f"headers 不是有效 JSON: {exc.msg}") from exc
    return normalize_headers(raw)


def _parse_field(field_name: str, value: str) -> Any:
    if field_name == "base_url":
        return normalize_base_url(_strip_outer_quotes(value))
    if field_name == "api_key":
        key = _strip_outer_quotes(value)
        if not key:
            raise ApiProfileError("API Key 不能为空")
        if "\r" in key or "\n" in key:
            raise ApiProfileError("API Key 不能包含换行")
        return key
    if field_name == "model":
        return normalize_model_name(_strip_outer_quotes(value))
    if field_name == "api_mode":
        return normalize_api_mode(_strip_outer_quotes(value))
    if field_name == "reasoning_effort":
        reasoning = _strip_outer_quotes(value).lower()
        if not reasoning or any(ch.isspace() for ch in reasoning):
            raise ApiProfileError("reasoning_effort 必须是单个非空词")
        return reasoning
    if field_name == "web_search":
        return _parse_bool(value)
    if field_name == "native_multimodal":
        return _parse_bool(value)
    if field_name == "headers":
        return _parse_headers(value)
    raise ApiProfileError(f"未知字段: {field_name}")


def _field_prompt(field_name: str) -> str:
    prompts = {
        "base_url": "请输入 base_url；官方默认地址请输入 default，或输入 skip 使用默认地址：",
        "api_key": "请输入 API Key；内容不会回显，必填项，不能 skip：",
        "model": "请输入完整模型名，例如 Claude Fable 5.1；会保留空格和大小写，必填项：",
        "api_mode": "请输入 API 模式 chat 或 responses；输入 skip 使用 chat：",
        "reasoning_effort": "请输入 reasoning_effort，例如 none/low/medium/high；输入 skip 使用 low：",
        "web_search": "是否启用服务端 web_search？on/off，输入 skip 使用 on：",
        "native_multimodal": "是否启用原生多模态？on/off，输入 skip 使用 on：",
        "headers": '请输入额外请求头 JSON 对象，例如 {"X-Test":"1"}；输入 skip 使用空对象：',
    }
    return prompts.get(field_name, f"请输入 {field_name}：")


def _redacted_value(field_name: str, value: Any) -> str:
    if field_name == "api_key":
        text = str(value)
        return f"已设置(长度 {len(text)})" if text else "未设置"
    if field_name == "headers":
        headers = {str(k): str(v) for k, v in value.items()} if isinstance(value, dict) else {}
        return json.dumps(redact_headers(headers), ensure_ascii=False, sort_keys=True)
    return str(value)


def _format_draft(profile_name: str, draft: dict[str, Any]) -> str:
    lines = [f"profile: {profile_name}"]
    for field_name in _EDITABLE_FIELDS:
        if field_name in draft:
            lines.append(f"{field_name}: {_redacted_value(field_name, draft[field_name])}")
    return "\n".join(lines)


class ApiProfileWizard:
    """Collect profile fields one message at a time without storing secrets on disk."""

    def __init__(self, manager: ApiProfileManager) -> None:
        self.manager = manager
        self._sessions: dict[int, WizardSession] = {}
        self._locks: dict[int, asyncio.Lock] = {}

    def _lock_for(self, uid: int) -> asyncio.Lock:
        lock = self._locks.get(uid)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[uid] = lock
        return lock

    def _expire_if_needed(self, uid: int) -> WizardSession | None:
        session = self._sessions.get(uid)
        if session is None:
            return None
        if time.monotonic() - session.updated_at > WIZARD_TIMEOUT:
            self._sessions.pop(uid, None)
            return None
        return session

    def expects_secret(self, uid: int) -> bool:
        """Return whether the next message is consumed as an API key value."""
        session = self._expire_if_needed(uid)
        if session is None or session.kind == "remove":
            return False
        step = session.steps[session.index]
        return step == "api_key" or (step == "__value__" and session.edit_field == "api_key")

    async def start_add(self, uid: int) -> str:
        async with self._lock_for(uid):
            if self._expire_if_needed(uid) is not None:
                return "已有 API 配置向导进行中，请先 confirm 或 cancel"
            session = WizardSession(
                uid=uid,
                kind="add",
                profile_name="",
                steps=list(_ADD_STEPS),
                index=0,
                draft={
                    "base_url": "",
                    "api_key": "",
                    "model": "",
                    "api_mode": "chat",
                    "reasoning_effort": "low",
                    "web_search": True,
                    "native_multimodal": True,
                    "headers": {},
                },
            )
            self._sessions[uid] = session
            return self._prompt(session)

    async def start_set(self, uid: int, profile_name: str, field_name: str = "") -> str:
        async with self._lock_for(uid):
            if self._expire_if_needed(uid) is not None:
                return "已有 API 配置向导进行中，请先 confirm 或 cancel"
            try:
                profile = self.manager.get_profile(validate_profile_name(profile_name))
            except ApiProfileError as exc:
                return repr(exc)

            selected = _FIELD_ALIASES.get(field_name.strip().lower(), "") if field_name else ""
            if field_name and not selected:
                return f"未知字段「{field_name}」，可用字段: {', '.join(_EDITABLE_FIELDS)}"
            steps = [selected, "__confirm__"] if selected else ["__select_field__", "__value__", "__confirm__"]
            session = WizardSession(
                uid=uid,
                kind="set",
                profile_name=profile.name,
                steps=steps,
                index=0,
                draft=profile.to_dict(),
                original=profile,
                edit_field=selected or None,
            )
            self._sessions[uid] = session
            if selected:
                return _field_prompt(selected)
            return (
                "请选择要修改的字段:\n"
                + "、".join(_EDITABLE_FIELDS)
                + "\n字段也可使用 url/key/md/mode/reason/web/multi/hdr 缩写。"
            )

    async def start_remove(self, uid: int, profile_name: str) -> str:
        async with self._lock_for(uid):
            if self._expire_if_needed(uid) is not None:
                return "已有 API 配置向导进行中，请先 confirm 或 cancel"
            try:
                profile = self.manager.get_profile(validate_profile_name(profile_name))
            except ApiProfileError as exc:
                return repr(exc)
            session = WizardSession(
                uid=uid,
                kind="remove",
                profile_name=profile.name,
                steps=["__remove_confirm__"],
                index=0,
                draft=profile.redacted_dict(),
                original=profile,
            )
            self._sessions[uid] = session
            return (
                f"即将删除 API profile「{profile.name}」:\n"
                f"{_format_draft(profile.name, profile.to_dict())}\n"
                f"输入 `confirm {profile.name}` 删除，或输入 cancel 取消。"
            )

    async def handle_message(self, uid: int, text: str) -> WizardReply | None:
        async with self._lock_for(uid):
            session = self._expire_if_needed(uid)
            if session is None:
                return None
            session.updated_at = time.monotonic()
            command = text.strip()
            lowered = command.lower()

            if lowered == "cancel":
                self._sessions.pop(uid, None)
                return WizardReply("已取消 API 配置向导。")
            if lowered == "show":
                return WizardReply(_format_draft(session.profile_name or "(待填写)", session.draft))
            if lowered == "back":
                if session.index <= 0:
                    return WizardReply("已经是第一项，可输入 cancel 取消。")
                session.index -= 1
                return WizardReply(self._prompt(session))
            if lowered == "skip":
                return self._skip(session)
            if session.kind == "remove":
                return await self._handle_remove_confirm(session, command)
            if session.kind == "set" and session.steps[session.index] == "__select_field__":
                return self._select_field(session, lowered)

            step = session.steps[session.index]
            if step == "__confirm__":
                if lowered not in ("confirm", "yes", "y", "确认"):
                    return WizardReply("输入 confirm 保存，back 返回修改，cancel 放弃。")
                return await self._save(session)
            if step == "__value__":
                if session.edit_field is None:
                    return WizardReply("内部状态错误：未选择字段，请 cancel 后重新开始。")
                return self._set_field_value(session, session.edit_field, command)
            if step == "__name__":
                try:
                    session.profile_name = validate_profile_name(_strip_outer_quotes(command))
                except ApiProfileError as exc:
                    return WizardReply(repr(exc))
                return self._advance(session)
            return self._set_field_value(session, step, command)

    def _prompt(self, session: WizardSession) -> str:
        step = session.steps[session.index]
        if step == "__name__":
            return "请输入 API profile 名称(字母、数字、点、下划线、连字符)："
        if step == "__select_field__":
            return (
                "请选择要修改的字段:\n"
                + "、".join(_EDITABLE_FIELDS)
                + "\n字段也可使用 url/key/md/mode/reason/web/multi/hdr 缩写。"
            )
        if step == "__confirm__":
            return (
                f"即将保存 API profile「{session.profile_name}」:\n"
                f"{_format_draft(session.profile_name, session.draft)}\n"
                "输入 confirm 保存，back 返回修改，cancel 放弃。"
            )
        if step == "__value__":
            if session.edit_field is None:
                return "请选择要修改的字段："
            return _field_prompt(session.edit_field)
        return _field_prompt(step)

    def _advance(self, session: WizardSession) -> WizardReply:
        session.index += 1
        return WizardReply(self._prompt(session))

    def _skip(self, session: WizardSession) -> WizardReply:
        step = session.steps[session.index]
        field_name = session.edit_field if step == "__value__" else step
        if field_name is None:
            return WizardReply("当前没有可跳过的字段。")
        if field_name not in _OPTIONAL_FIELDS:
            return WizardReply(f"{field_name or '当前字段'} 是必填项，不能 skip。")
        defaults: dict[str, Any] = {
            "base_url": "",
            "api_mode": "chat",
            "reasoning_effort": "low",
            "web_search": True,
            "native_multimodal": True,
            "headers": dict[str, str](),
        }
        session.draft[field_name] = defaults[field_name]
        return self._advance(session)

    def _select_field(self, session: WizardSession, value: str) -> WizardReply:
        field_name = _FIELD_ALIASES.get(value)
        if field_name is None:
            return WizardReply(f"未知字段「{value}」，可用字段: {', '.join(_EDITABLE_FIELDS)}")
        session.edit_field = field_name
        session.steps[1] = "__value__"
        session.index = 1
        return WizardReply(_field_prompt(field_name))

    def _set_field_value(self, session: WizardSession, field_name: str, value: str) -> WizardReply:
        try:
            session.draft[field_name] = _parse_field(field_name, value)
        except ApiProfileError as exc:
            return WizardReply(repr(exc))
        return self._advance(session)

    async def _save(self, session: WizardSession) -> WizardReply:
        try:
            profile = ApiProfile(
                name=session.profile_name,
                base_url=str(session.draft.get("base_url") or ""),
                api_key=str(session.draft.get("api_key") or ""),
                model=str(session.draft.get("model") or ""),
                api_mode=normalize_api_mode(str(session.draft.get("api_mode") or "chat")),
                reasoning_effort=str(session.draft.get("reasoning_effort") or "low"),
                web_search=bool(session.draft.get("web_search", True)),
                native_multimodal=bool(session.draft.get("native_multimodal", True)),
                headers=session.draft.get("headers") if isinstance(session.draft.get("headers"), dict) else {},
            )
            if session.kind == "add":
                await self.manager.add_profile(profile)
                action = "已新增"
            else:
                await self.manager.update_profile(profile)
                action = "已更新"
        except (ApiProfileError, OSError) as exc:
            return WizardReply(f"保存失败: {exc}")
        self._sessions.pop(session.uid, None)
        prefix = "当前 active profile 已同步更新。" if session.profile_name == self.manager.active_profile else ""
        return WizardReply(f"{action} API profile「{profile.name}」。{prefix}")

    async def _handle_remove_confirm(self, session: WizardSession, command: str) -> WizardReply:
        expected = f"confirm {session.profile_name}"
        if command.lower() != expected.lower():
            return WizardReply(f"确认文本不匹配。请输入 `{expected}`，或输入 cancel 取消。")
        try:
            await self.manager.remove_profile(session.profile_name)
        except (ApiProfileError, OSError) as exc:
            return WizardReply(f"删除失败: {exc}")
        self._sessions.pop(session.uid, None)
        return WizardReply(f"已删除 API profile「{session.profile_name}」。")


__all__ = ["ApiProfileWizard", "WIZARD_TIMEOUT", "WizardReply"]
