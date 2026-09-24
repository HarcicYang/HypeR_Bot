"""Agent profile loading and persistence."""

import contextlib
import dataclasses
import json
import os
import time
from typing import Any

from hyperot import configurator

config = configurator.BotConfig.get("hyper-bot")
PROFILES_PATH = "./profiles.json"
PROFILE_SWITCH_PATH = "./temps/agent_profile_switch.json"


@dataclasses.dataclass(frozen=True)
class AgentProfile:
    prompt: str
    inject_master: bool = True


def profile_from_value(value: object) -> AgentProfile | None:
    if isinstance(value, str):
        prompt = value.strip()
        return AgentProfile(prompt) if prompt else None
    if isinstance(value, dict):
        prompt = value.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            return None
        enabled = value.get("inject_master", True)
        return AgentProfile(prompt.strip(), enabled if isinstance(enabled, bool) else True)
    return None


def profile_to_value(profile: AgentProfile) -> dict[str, str | bool]:
    return {"prompt": profile.prompt, "inject_master": profile.inject_master}


def save_profiles(profiles: dict[str, AgentProfile]) -> None:
    with open(PROFILES_PATH, "w", encoding="utf-8") as f:
        json.dump({name: profile_to_value(p) for name, p in profiles.items()}, f, indent=2, ensure_ascii=False)


def load_profiles(default_prompt: str) -> dict[str, AgentProfile]:
    try:
        with open(PROFILES_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            profiles = {
                str(name): profile for name, value in data.items() if (profile := profile_from_value(value)) is not None
            }
            if profiles:
                return profiles
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    fallback = {"cat": AgentProfile(default_prompt)}
    with contextlib.suppress(OSError):
        save_profiles(fallback)
    return fallback


def current_profile_name() -> str:
    return str(config.others.get("agent_profile") or "cat")


def mark_profile_switch(name: str) -> dict[str, Any]:
    """Persist the last global profile switch timestamp."""
    data = {"profile": name, "switched_at": time.time()}
    directory = os.path.dirname(PROFILE_SWITCH_PATH)
    if directory:
        os.makedirs(directory, exist_ok=True)
    tmp = PROFILE_SWITCH_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
    os.replace(tmp, PROFILE_SWITCH_PATH)
    return data


def load_profile_switch() -> dict[str, Any] | None:
    try:
        with open(PROFILE_SWITCH_PATH, encoding="utf-8") as file:
            data = json.load(file)
    except (FileNotFoundError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def history_needs_profile_summary(history_path: str) -> bool:
    """Return whether a Main history predates the last global profile switch."""
    state = load_profile_switch()
    if state is None or not os.path.isfile(history_path):
        return False
    try:
        switched_at = float(state.get("switched_at") or 0)
        return os.path.getmtime(history_path) < switched_at
    except OSError:
        return False
