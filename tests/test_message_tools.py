"""collected_send 多节点合并转发测试。"""

from __future__ import annotations

import importlib
import os
import sys
import types
import unittest
from types import SimpleNamespace
from typing import Any

from typing_extensions import override

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_message_tools() -> Any:
    """加载 message_tools,绕开 modules/__init__.py 的模块扫描。"""
    if "test_message_tools_module" in sys.modules:
        return sys.modules["test_message_tools_module"]
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    stubs: dict[str, types.ModuleType] = {}
    for name, rel in (
        ("modules", "modules"),
        ("modules.AgentTools", os.path.join("modules", "AgentTools")),
        ("modules.AgentRuntime", os.path.join("modules", "AgentRuntime")),
    ):
        if name not in sys.modules:
            pkg = types.ModuleType(name)
            pkg.__path__ = [os.path.join(ROOT, rel)]  # type: ignore[attr-defined]
            sys.modules[name] = pkg
            stubs[name] = pkg
    try:
        from hyperot import configurator

        if "hyper-bot" not in configurator.BotConfig._loaded_cfgs:
            configurator.BotConfig._loaded_cfgs["hyper-bot"] = configurator.BotConfig(
                protocol="OneBot",
                owner=[],
                black_list=[],
                silents=[],
                connection={"mode": "FWS", "host": "127.0.0.1", "port": 0},
                uin=0,
                others={},
            )
        module = importlib.import_module("modules.AgentTools.message_tools")
    finally:
        for name in stubs:
            sys.modules.pop(name, None)
    sys.modules["test_message_tools_module"] = module
    return module


MESSAGE = _load_message_tools()
REGISTRY = sys.modules["modules.AgentTools.registry"]


class _FakeActions:
    def __init__(self) -> None:
        self.sent: list[Any] = []

    def group(self, scene_id: str) -> _FakeActions:
        return self

    def user(self, scene_id: str) -> _FakeActions:
        return self

    async def send(self, message: Any) -> Any:
        self.sent.append(message)
        return SimpleNamespace(message_id=777)


class CollectedSendTests(unittest.IsolatedAsyncioTestCase):
    @override
    def setUp(self) -> None:
        self.tools = MESSAGE.MessageTools()
        self.actions = _FakeActions()
        self.ctx = REGISTRY.ToolContext(
            actions=self.actions,
            ev_type="group",
            scene_id=100,
            principal_id=10001,
            self_id=30003,
        )

    def _nodes(self, index: int = 0) -> list[dict[str, Any]]:
        message = self.actions.sent[index]
        segment = next(iter(message))
        self.assertEqual(segment.wire_type, "forward")
        nodes = segment.data["content"]
        wire = MESSAGE._codec.encode_segments(message)
        self.assertEqual(wire, [{"type": "forward", "data": {"content": nodes}}])
        return nodes

    async def test_schema_exposes_typed_nodes(self) -> None:
        registration = next(item for item in REGISTRY.ToolRegistry.registrations() if item.name == "collected_send")
        nodes = registration.schema["properties"]["nodes"]
        self.assertEqual(nodes["type"], "array")
        self.assertEqual(nodes["items"]["properties"]["message"]["type"], "array")
        self.assertIn("user_id", nodes["items"]["properties"])
        self.assertNotIn("nickname", nodes["items"]["properties"])
        self.assertNotIn("nodes", registration.required)
        self.assertNotIn("message", registration.required)

    async def test_single_message_remains_backward_compatible(self) -> None:
        result = await self.tools.collected_send(
            self.ctx,
            message=[{"seg": "text", "text": "旧调用"}],
            group_id=100,
        )
        self.assertEqual(result, "合并转发发送成功：group_id=100，message_id=777")
        nodes = self._nodes()
        self.assertEqual(len(nodes), 1)
        self.assertEqual(nodes[0]["data"]["user_id"], "30003")
        self.assertEqual(nodes[0]["data"]["nickname"], "")
        self.assertEqual(nodes[0]["data"]["content"][0]["data"]["text"], "旧调用")

    async def test_multiple_nodes_can_specify_users(self) -> None:
        result = await REGISTRY.ToolRegistry.dispatch(
            "collected_send",
            {
                "nodes": [
                    {
                        "user_id": "10001",
                        "message": [{"seg": "text", "text": "第一条"}],
                    },
                    {
                        "user_id": 20002,
                        "message": [
                            {"seg": "text", "text": "第二条"},
                            {"seg": "at", "qq": "10001"},
                        ],
                    },
                    {"message": [{"seg": "text", "text": "默认 Bot 节点"}]},
                ],
                "user_id": 99999,
            },
            self.ctx,
        )
        self.assertEqual(result, "合并转发发送成功：user_id=99999，message_id=777")
        nodes = self._nodes()
        self.assertEqual([node["data"]["user_id"] for node in nodes], ["10001", "20002", "30003"])
        self.assertEqual([node["data"]["nickname"] for node in nodes], ["", "", ""])
        self.assertEqual(nodes[0]["data"]["content"][0]["data"]["text"], "第一条")
        self.assertEqual(nodes[1]["data"]["content"][1]["type"], "at")
        self.assertEqual(nodes[1]["data"]["content"][1]["data"]["qq"], "10001")

    async def test_invalid_nodes_are_rejected(self) -> None:
        cases: tuple[dict[str, Any], ...] = (
            {},
            {
                "message": [{"seg": "text", "text": "single"}],
                "nodes": [{"message": [{"seg": "text", "text": "multi"}]}],
            },
            {"nodes": []},
            {"nodes": [{"message": [{"seg": "text", "text": str(index)}]} for index in range(101)]},
            {"nodes": [{"message": [{"seg": "text", "text": "x"}], "unknown": True}]},
            {"nodes": [{"nickname": "x", "message": [{"seg": "text", "text": "x"}]}]},
            {"nodes": [{"user_id": 0, "message": [{"seg": "text", "text": "x"}]}]},
        )
        for kwargs in cases:
            with self.subTest(kwargs=kwargs):
                result = await self.tools.collected_send(self.ctx, group_id=100, **kwargs)
                self.assertTrue(result.startswith("调用不合法："), result)
        self.assertEqual(self.actions.sent, [])


if __name__ == "__main__":
    unittest.main()
