"""Persistent API provider profiles and runtime client management."""

from __future__ import annotations

import asyncio
import dataclasses
import json
import os
import re
import stat
from dataclasses import dataclass, field
from typing import Any, Literal, cast
from urllib.parse import urlparse

from openai import AsyncOpenAI

API_PROFILES_PATH = "./api_profiles.json"
CONFIG_PATH = "config.json"
SCHEMA_VERSION = 1

_PROFILE_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,32}$")
_RESERVED_PROFILE_NAMES = {
    "add",
    "api",
    "confirm",
    "ls",
    "reload",
    "rl",
    "rm",
    "set",
    "sh",
    "show",
}
_LEGACY_CONFIG_KEYS = {
    "agent_api",
    "agent_native_multimodal",
    "agent_reasoning_effort",
    "agent_web_search",
    "openai_endpoint",
    "openai_key",
    "openai_model",
}


class ApiProfileError(ValueError):
    """Invalid API profile data or lifecycle operation."""


def validate_profile_name(name: str) -> str:
    value = name.strip()
    if not _PROFILE_NAME_RE.fullmatch(value):
        raise ApiProfileError("profile 名称只能包含字母、数字、点、下划线和连字符，最长 32 个字符")
    if value.lower() in _RESERVED_PROFILE_NAMES:
        raise ApiProfileError(f"profile 名称「{value}」是保留命令词")
    return value


def normalize_model_name(value: str, *, allow_empty: bool = False) -> str:
    model = value.strip()
    if not model:
        if allow_empty:
            return ""
        raise ApiProfileError("模型名称不能为空")
    if len(model) > 256:
        raise ApiProfileError("模型名称过长(最多 256 个字符)")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in model):
        raise ApiProfileError("模型名称不能包含控制字符")
    return model


def normalize_base_url(value: str) -> str:
    url = value.strip()
    if not url or url.lower() == "default":
        return ""
    if any(ch.isspace() for ch in url):
        raise ApiProfileError("base_url 不能包含空白字符")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ApiProfileError("base_url 必须是 http(s) URL，或输入 default")
    return url


def normalize_api_mode(value: str) -> Literal["chat", "responses"]:
    mode = value.strip().lower()
    if mode not in ("chat", "responses"):
        raise ApiProfileError("API 模式必须是 chat 或 responses")
    return cast(Literal["chat", "responses"], mode)


def normalize_headers(value: Any) -> dict[str, str]:
    if value in (None, ""):
        return {}
    if not isinstance(value, dict):
        raise ApiProfileError("headers 必须是 JSON 对象")
    headers: dict[str, str] = {}
    for raw_name, raw_value in value.items():
        name = str(raw_name).strip()
        if not name or any(ch in name for ch in "\r\n:"):
            raise ApiProfileError(f"无效的请求头名称: {raw_name!r}")
        text = str(raw_value)
        if "\r" in text or "\n" in text:
            raise ApiProfileError(f"请求头 {name} 的值不能包含换行")
        headers[name] = text
    return headers


def redact_headers(headers: dict[str, str]) -> dict[str, str]:
    markers = ("authorization", "api-key", "apikey", "token", "secret", "cookie")
    redacted: dict[str, str] = {}
    for name, value in headers.items():
        if any(marker in name.lower() for marker in markers):
            redacted[name] = f"已设置(长度 {len(value)})" if value else "未设置"
        else:
            redacted[name] = value
    return redacted


def _normalize_bool(value: Any, field_name: str, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ("on", "true", "1", "yes", "开", "开启"):
            return True
        if normalized in ("off", "false", "0", "no", "关", "关闭"):
            return False
    raise ApiProfileError(f"{field_name} 必须是布尔值")


@dataclass(frozen=True)
class ApiProfile:
    name: str
    base_url: str
    api_key: str
    model: str
    api_mode: Literal["chat", "responses"] = "chat"
    reasoning_effort: str = "low"
    web_search: bool = True
    native_multimodal: bool = True
    headers: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", validate_profile_name(self.name))
        object.__setattr__(self, "base_url", normalize_base_url(self.base_url))
        object.__setattr__(self, "api_key", self.api_key.strip())
        object.__setattr__(self, "model", normalize_model_name(self.model, allow_empty=True))
        object.__setattr__(self, "api_mode", normalize_api_mode(self.api_mode))
        reasoning = self.reasoning_effort.strip() or "low"
        if any(ch.isspace() for ch in reasoning):
            raise ApiProfileError("reasoning_effort 不能包含空白字符")
        object.__setattr__(self, "reasoning_effort", reasoning)
        object.__setattr__(self, "headers", normalize_headers(self.headers))

    @classmethod
    def from_dict(cls, name: str, raw: dict[str, Any]) -> ApiProfile:
        return cls(
            name=name,
            base_url=str(raw.get("base_url") or ""),
            api_key=str(raw.get("api_key") or ""),
            model=str(raw.get("model") or ""),
            api_mode=cast(Literal["chat", "responses"], raw.get("api_mode") or "chat"),
            reasoning_effort=str(raw.get("reasoning_effort") or "low"),
            web_search=_normalize_bool(raw.get("web_search"), "web_search", True),
            native_multimodal=_normalize_bool(raw.get("native_multimodal"), "native_multimodal", True),
            headers=raw.get("headers") if isinstance(raw.get("headers"), dict) else {},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_url": self.base_url,
            "api_key": self.api_key,
            "model": self.model,
            "api_mode": self.api_mode,
            "reasoning_effort": self.reasoning_effort,
            "web_search": self.web_search,
            "native_multimodal": self.native_multimodal,
            "headers": dict(self.headers),
        }

    @property
    def fingerprint(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    def redacted_dict(self) -> dict[str, Any]:
        data = self.to_dict()
        key = self.api_key
        data["api_key"] = f"已设置(长度 {len(key)})" if key else "未设置"
        data["headers"] = redact_headers(self.headers)
        return data


@dataclass(frozen=True)
class ApiRuntime:
    profile: ApiProfile
    client: AsyncOpenAI

    @property
    def fingerprint(self) -> str:
        return self.profile.fingerprint


def _read_json(path: str) -> dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as file:
            raw = json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        raise ApiProfileError(f"读取 {path} 失败: {exc}") from exc
    if not isinstance(raw, dict):
        raise ApiProfileError(f"{path} 顶层必须是 JSON 对象")
    return raw


def _atomic_write_json(path: str, data: dict[str, Any], *, private: bool = False) -> None:
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    existing_mode = stat.S_IMODE(os.stat(path).st_mode) if os.path.exists(path) else None
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=2)
            file.flush()
            os.fsync(file.fileno())
        if os.name != "nt":
            if private:
                os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)
            elif existing_mode is not None:
                os.chmod(tmp, existing_mode)
        os.replace(tmp, path)
        if os.name != "nt":
            if private:
                os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
            elif existing_mode is not None:
                os.chmod(path, existing_mode)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


class ApiProfileManager:
    """Own active profile state and lazily cache one OpenAI client per profile."""

    def __init__(
        self,
        profiles: dict[str, ApiProfile],
        active_profile: str,
        *,
        profiles_path: str = API_PROFILES_PATH,
        config_path: str = CONFIG_PATH,
    ) -> None:
        if not profiles:
            raise ApiProfileError("至少需要一个 API profile")
        if active_profile not in profiles:
            raise ApiProfileError(f"active_profile「{active_profile}」不存在")
        self.profiles = profiles
        self.active_profile = active_profile
        self.profiles_path = profiles_path
        self.config_path = config_path
        self._clients: dict[str, tuple[str, AsyncOpenAI]] = {}
        self._lock = asyncio.Lock()

    @classmethod
    def load(
        cls,
        others: dict[str, Any],
        *,
        profiles_path: str = API_PROFILES_PATH,
        config_path: str = CONFIG_PATH,
    ) -> ApiProfileManager:
        if os.path.isfile(profiles_path):
            manager = cls._load_current(profiles_path, config_path)
            manager._prune_legacy_config(others)
            return manager

        profile = ApiProfile(
            name="default",
            base_url=str(others.get("openai_endpoint") or ""),
            api_key=str(others.get("openai_key") or ""),
            model=str(others.get("openai_model") or ""),
            api_mode=cast(Literal["chat", "responses"], others.get("agent_api") or "chat"),
            reasoning_effort=str(others.get("agent_reasoning_effort") or "low"),
            web_search=_normalize_bool(others.get("agent_web_search"), "agent_web_search", True),
            native_multimodal=_normalize_bool(
                others.get("agent_native_multimodal"),
                "agent_native_multimodal",
                True,
            ),
        )
        manager = cls({"default": profile}, "default", profiles_path=profiles_path, config_path=config_path)
        manager._save()
        manager._prune_legacy_config(others)
        return manager

    @classmethod
    def _load_current(cls, profiles_path: str, config_path: str) -> ApiProfileManager:
        raw = _read_json(profiles_path)
        version = raw.get("version", SCHEMA_VERSION)
        if version != SCHEMA_VERSION:
            raise ApiProfileError(f"不支持的 api_profiles 版本: {version!r}")
        raw_profiles = raw.get("profiles")
        if not isinstance(raw_profiles, dict) or not raw_profiles:
            raise ApiProfileError("api_profiles.json 缺少非空 profiles 对象")
        profiles: dict[str, ApiProfile] = {}
        for name, value in raw_profiles.items():
            if not isinstance(value, dict):
                raise ApiProfileError(f"profile「{name}」必须是 JSON 对象")
            profile = ApiProfile.from_dict(str(name), value)
            profiles[profile.name] = profile
        active = str(raw.get("active_profile") or "")
        if active not in profiles:
            raise ApiProfileError(f"active_profile「{active}」不存在")
        return cls(profiles, active, profiles_path=profiles_path, config_path=config_path)

    def _serialize(self) -> dict[str, Any]:
        return {
            "version": SCHEMA_VERSION,
            "active_profile": self.active_profile,
            "profiles": {name: profile.to_dict() for name, profile in self.profiles.items()},
        }

    def _save(self) -> None:
        try:
            _atomic_write_json(self.profiles_path, self._serialize(), private=True)
        except OSError as exc:
            raise ApiProfileError(f"保存 {self.profiles_path} 失败: {exc}") from exc

    def _prune_legacy_config(self, others: dict[str, Any]) -> None:
        changed = False
        for key in _LEGACY_CONFIG_KEYS:
            if key in others:
                others.pop(key, None)
                changed = True
        if not changed or not os.path.isfile(self.config_path):
            return
        raw = _read_json(self.config_path)
        raw_others = raw.get("others")
        if isinstance(raw_others, dict):
            for key in _LEGACY_CONFIG_KEYS:
                raw_others.pop(key, None)
        try:
            _atomic_write_json(self.config_path, raw)
        except OSError as exc:
            raise ApiProfileError(f"清理旧 API 配置失败: {exc}") from exc

    def _build_client(self, profile: ApiProfile) -> AsyncOpenAI:
        headers = dict(profile.headers)
        headers["User-Agent"] = ""
        api_key = profile.api_key or "not-configured"
        if profile.base_url:
            return AsyncOpenAI(api_key=api_key, base_url=profile.base_url, default_headers=headers)
        return AsyncOpenAI(api_key=api_key, default_headers=headers)

    def snapshot(self, name: str | None = None) -> ApiRuntime:
        profile_name = name or self.active_profile
        profile = self.profiles.get(profile_name)
        if profile is None:
            raise ApiProfileError(f"API profile「{profile_name}」不存在")
        cached = self._clients.get(profile.name)
        if cached is not None and cached[0] == profile.fingerprint:
            return ApiRuntime(profile=profile, client=cached[1])
        client = self._build_client(profile)
        self._clients[profile.name] = (profile.fingerprint, client)
        return ApiRuntime(profile=profile, client=client)

    def get_profile(self, name: str) -> ApiProfile:
        profile = self.profiles.get(name)
        if profile is None:
            raise ApiProfileError(f"API profile「{name}」不存在")
        return profile

    async def add_profile(self, profile: ApiProfile) -> None:
        async with self._lock:
            if profile.name in self.profiles:
                raise ApiProfileError(f"API profile「{profile.name}」已存在")
            previous = dict(self.profiles)
            self.profiles = {**self.profiles, profile.name: profile}
            try:
                self._save()
            except ApiProfileError:
                self.profiles = previous
                raise

    async def update_profile(self, profile: ApiProfile) -> None:
        async with self._lock:
            if profile.name not in self.profiles:
                raise ApiProfileError(f"API profile「{profile.name}」不存在")
            previous = dict(self.profiles)
            self.profiles = {**self.profiles, profile.name: profile}
            try:
                self._save()
            except ApiProfileError:
                self.profiles = previous
                raise

    async def set_active(self, name: str) -> ApiProfile:
        async with self._lock:
            profile = self.get_profile(name)
            previous = self.active_profile
            self.active_profile = profile.name
            try:
                self._save()
            except ApiProfileError:
                self.active_profile = previous
                raise
            return profile

    async def set_active_model(self, model: str) -> ApiProfile:
        async with self._lock:
            current = self.get_profile(self.active_profile)
            updated = dataclasses.replace(current, model=normalize_model_name(model))
            previous = dict(self.profiles)
            self.profiles = {**self.profiles, updated.name: updated}
            try:
                self._save()
            except ApiProfileError:
                self.profiles = previous
                raise
            return updated

    async def remove_profile(self, name: str) -> ApiProfile:
        async with self._lock:
            profile = self.get_profile(name)
            if profile.name == self.active_profile:
                raise ApiProfileError("不能删除当前 active profile")
            if len(self.profiles) <= 1:
                raise ApiProfileError("至少需要保留一个 API profile")
            previous = dict(self.profiles)
            self.profiles = {key: value for key, value in self.profiles.items() if key != profile.name}
            try:
                self._save()
            except ApiProfileError:
                self.profiles = previous
                raise
            self._clients.pop(profile.name, None)
            return profile

    async def reload(self) -> None:
        async with self._lock:
            loaded = self._load_current(self.profiles_path, self.config_path)
            self.profiles = loaded.profiles
            self.active_profile = loaded.active_profile
            valid_names = set(self.profiles)
            for name in list(self._clients):
                if name not in valid_names:
                    self._clients.pop(name, None)

    async def aclose(self) -> None:
        clients = [client for _, client in self._clients.values()]
        self._clients.clear()
        for client in clients:
            await client.close()


__all__ = [
    "API_PROFILES_PATH",
    "ApiProfile",
    "ApiProfileError",
    "ApiProfileManager",
    "ApiRuntime",
    "normalize_api_mode",
    "normalize_base_url",
    "normalize_headers",
    "normalize_model_name",
    "redact_headers",
    "validate_profile_name",
]
