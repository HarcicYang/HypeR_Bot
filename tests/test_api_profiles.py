from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from typing import Any

from typing_extensions import override

ROOT = Path(__file__).resolve().parents[1]


def _load_agent_runtime_modules() -> tuple[Any, Any]:
    """Load API profile modules without executing modules/__init__.py."""
    if "test_modules_api_profiles" in sys.modules:
        return sys.modules["test_modules_api_profiles"], sys.modules["test_modules_api_wizard"]

    package_root = "test_modules"
    runtime_root = "test_modules.AgentRuntime"
    pkg = types.ModuleType(package_root)
    pkg.__path__ = [str(ROOT / "modules")]  # type: ignore[attr-defined]
    runtime_pkg = types.ModuleType(runtime_root)
    runtime_pkg.__path__ = [str(ROOT / "modules" / "AgentRuntime")]  # type: ignore[attr-defined]
    sys.modules[package_root] = pkg
    sys.modules[runtime_root] = runtime_pkg

    profiles = importlib.import_module("test_modules.AgentRuntime.api_profiles")
    wizard = importlib.import_module("test_modules.AgentRuntime.api_wizard")
    sys.modules["test_modules_api_profiles"] = profiles
    sys.modules["test_modules_api_wizard"] = wizard
    return profiles, wizard


API_PROFILES, API_WIZARD = _load_agent_runtime_modules()


class ApiProfileTests(unittest.IsolatedAsyncioTestCase):
    @override
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.config_path = os.path.join(self.temp_dir.name, "config.json")
        self.profiles_path = os.path.join(self.temp_dir.name, "api_profiles.json")

    @override
    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _manager(self, others: dict[str, Any] | None = None) -> Any:
        with open(self.config_path, "w", encoding="utf-8") as file:
            json.dump({"others": dict(others or {})}, file)
        manager = API_PROFILES.ApiProfileManager.load(
            dict(others or {}),
            profiles_path=self.profiles_path,
            config_path=self.config_path,
        )
        return manager

    def test_legacy_config_migrates_and_removes_old_keys(self) -> None:
        others = {
            "openai_endpoint": "https://example.com/v1",
            "openai_key": "sk-test",
            "openai_model": "Claude Fable 5.1",
            "agent_api": "chat",
            "agent_reasoning_effort": "high",
            "agent_web_search": False,
            "agent_native_multimodal": True,
        }
        manager = self._manager(others)
        profile = manager.get_profile("default")

        self.assertEqual(profile.model, "Claude Fable 5.1")
        self.assertEqual(profile.api_key, "sk-test")
        self.assertEqual(profile.reasoning_effort, "high")
        self.assertFalse(profile.web_search)

        with open(self.profiles_path, encoding="utf-8") as file:
            persisted = json.load(file)
        self.assertEqual(persisted["profiles"]["default"]["model"], "Claude Fable 5.1")

        with open(self.config_path, encoding="utf-8") as file:
            cleaned = json.load(file)
        self.assertNotIn("openai_key", cleaned["others"])
        self.assertNotIn("openai_model", cleaned["others"])

    async def test_wizard_preserves_exact_model_and_redacts_key(self) -> None:
        manager = self._manager()
        wizard = API_WIZARD.ApiProfileWizard(manager)
        uid = 10001

        await wizard.start_add(uid)
        for value in (
            "Rinko",
            "https://example.com/v1",
            "sk-secret",
            "Claude Fable 5.1",
            "chat",
            "high",
            "off",
            "on",
            "skip",
        ):
            reply = await wizard.handle_message(uid, value)
            self.assertIsNotNone(reply)

        saved = await wizard.handle_message(uid, "confirm")
        self.assertIsNotNone(saved)
        profile = manager.get_profile("Rinko")
        self.assertEqual(profile.model, "Claude Fable 5.1")
        self.assertEqual(profile.api_key, "sk-secret")
        self.assertFalse(profile.web_search)

        shown = profile.redacted_dict()
        self.assertNotIn("sk-secret", json.dumps(shown))
        self.assertEqual(shown["api_key"], "已设置(长度 9)")

    async def test_switch_and_model_change_are_persisted(self) -> None:
        manager = self._manager()
        first = API_PROFILES.ApiProfile(
            name="first",
            base_url="https://first.example/v1",
            api_key="sk-first",
            model="Model One",
        )
        second = API_PROFILES.ApiProfile(
            name="second",
            base_url="https://second.example/v1",
            api_key="sk-second",
            model="Claude Fable 5.1",
        )
        await manager.add_profile(first)
        await manager.add_profile(second)
        await manager.set_active("second")
        await manager.set_active_model("Claude Fable 5.1 Pro")

        with open(self.profiles_path, encoding="utf-8") as file:
            persisted = json.load(file)
        self.assertEqual(persisted["active_profile"], "second")
        self.assertEqual(persisted["profiles"]["second"]["model"], "Claude Fable 5.1 Pro")

    def test_sensitive_headers_are_redacted(self) -> None:
        profile = API_PROFILES.ApiProfile(
            name="redacted",
            base_url="https://example.com/v1",
            api_key="sk-secret",
            model="Model Name",
            headers={"Authorization": "Bearer secret", "X-Trace": "visible"},
        )
        redacted = profile.redacted_dict()
        self.assertEqual(redacted["api_key"], "已设置(长度 9)")
        self.assertEqual(redacted["headers"]["Authorization"], "已设置(长度 13)")
        self.assertEqual(redacted["headers"]["X-Trace"], "visible")


if __name__ == "__main__":
    unittest.main()
