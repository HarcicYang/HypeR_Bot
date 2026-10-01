import json
import uuid
from typing import Any

from hyperot.v2 import (
    ClientAPI,
    Forward,
    Mention,
    Message,
    Quote,
    SceneType,
    Text,
    UnknownSegment,
)
from hyperot.v2.events import MessageReceivedEvent
from hyperot_adapter_onebot.segments import OneBotDice, OneBotSegmentCodec
from typing_extensions import override

import ModuleClass
from modules.OneBotExtraSegments import (
    KeyboardSegment,
    LongMessageSegment,
    MusicSegment,
    StreamSegment,
)

_codec = OneBotSegmentCodec()


def _unknown(payload: dict[str, Any]) -> UnknownSegment:
    """OneBot 原始段（{type, data}）→ UnknownSegment，wire 上原样透传。

    仅用于 inline 合并转发：``forward`` 这个 wire 类型已被适配器内置占用，
    注册自定义段需要 replace=True，会影响所有入站转发解码，故保留透传。
    """
    return UnknownSegment(wire_type=str(payload.get("type", "unknown")), data=payload.get("data") or {})


def _keyboard_button(
    text: str,
    style: int = 1,
    button_type: int = 2,
    data: str = "Hello World",
    enter: bool = False,
    permission: int = 2,
    specify_user_ids: Any = None,
) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "render_data": {"label": text, "visited_label": text, "style": style},
        "action": {
            "type": button_type,
            "permission": {"type": permission, "specify_user_ids": specify_user_ids},
            "enter": enter,
            "unsupport_tips": "Harcic",
            "data": data,
        },
    }


def _keyboard_segment(rows: list[dict[str, Any]]) -> KeyboardSegment:
    """QQ 自定义键盘：已注册进适配器段注册表的扩展段（wire: keyboard）。"""
    return KeyboardSegment(data={"content": {"rows": rows}, "bot_appid": 0})


def _forward_node(user_id: str, nickname: str, content: Message) -> dict[str, Any]:
    return {
        "type": "node",
        "data": {
            "user_id": user_id,
            "nickname": nickname,
            "content": _codec.encode_segments(content),
        },
    }


async def _send_forward(api: ClientAPI, scene_type: SceneType, scene_id: str, nodes: list[dict[str, Any]]) -> Any:
    """v2 尚无合并转发 action，直接调用 OneBot send_forward_msg 并返回响应 data。"""
    params: dict[str, Any] = {"message": nodes}
    if scene_type == SceneType.GROUP:
        params["group_id"] = int(scene_id)
    else:
        params["user_id"] = int(scene_id)
    result = await api.raw("send_forward_msg", params)
    return result.data if isinstance(result.data, dict) else dict[str, Any]()


@ModuleClass.ModuleRegister.register(MessageReceivedEvent)
class Test(ModuleClass.Module[MessageReceivedEvent]):
    @override
    @staticmethod
    def info() -> ModuleClass.ModuleInfo:
        return ModuleClass.ModuleInfo(
            is_hidden=True,
            module_name="TestMarkDown",
            desc="Markdown/消息类型测试模块",
            helps="主人专用测试模块，测试各种消息类型（键盘、转发节点、长消息等）",
        )

    @override
    async def handle(self):
        # 收到合并转发段（仅有 forward_id）时，用原始 get_forward_msg 解析节点并打印。
        for seg in self.event.message:
            if isinstance(seg, Forward):
                raw = await self.api.raw("get_forward_msg", {"id": seg.forward_id})
                payload: Any = raw.data
                data = payload if isinstance(payload, dict) else dict[str, Any]()
                for node in data.get("message") or []:
                    node_data = node.get("data", node) if isinstance(node, dict) else dict[str, Any]()
                    print(f"{node_data.get('nickname')}({node_data.get('user_id')}) {node_data.get('content')}")
                break

        if not ModuleClass.is_owner(self.event):
            return

        text = str(self.event.message)
        scene = self.api.scene(self.event.scene_type, self.event.scene_id)

        if text == ".test_h":
            row = {
                "buttons": [
                    _keyboard_button(
                        "Ciallo!",
                        data="我。。。我要做主人的新怒！🥵嗯…🥵哈～呃🥵～🥵🥵🥵🥵🥵主人最棒了！再深一点~🥵",
                        enter=True,
                    )
                ]
            }
            await scene.send(Message(_keyboard_segment([row])))

        elif text == ".test2_h":
            nodes = [
                _forward_node(
                    "2530894749",
                    'dext("⁧⁧ ("⁧‭',
                    Message(Mention(user_id="2488529467"), Text(text="好想🥵，好想被主人宠幸🥵")),
                )
            ]
            await scene.send(Message(_unknown({"type": "forward", "data": {"content": nodes}})))

        elif text == ".test3":
            profile = await self.api.user("2488529467").profile()
            print(profile.user_id, profile.display_name)
            await scene.send(
                Message(
                    Quote(message_id=str(self.event.message_id)),
                    Text(text=json.dumps(profile.model_dump(mode="json"), ensure_ascii=False)),
                )
            )

        elif text == "Ciallo～(∠・ω< )⌒★":
            row = {"buttons": [_keyboard_button("Ciallo～(∠・ω< )⌒★", data="https://ciallo.cc", button_type=0)]}
            nodes = [_forward_node(str(ModuleClass.self_id_of(self.event)), "bot", Message(_keyboard_segment([row])))]
            data = await _send_forward(self.api, self.event.scene_type, str(self.event.scene_id), nodes)
            res_id = data.get("forward_id") or data.get("message_id")
            if res_id:
                await scene.send(Message(LongMessageSegment(data={"id": str(res_id)})))

        elif text == "我们的小溯":
            row = {"buttons": [_keyboard_button("小溯溯真棒", data="👍", enter=True, style=0)]}
            nodes = [_forward_node(str(ModuleClass.self_id_of(self.event)), "bot", Message(_keyboard_segment([row])))]
            data = await _send_forward(self.api, self.event.scene_type, str(self.event.scene_id), nodes)
            res_id = data.get("forward_id") or data.get("message_id")
            if res_id:
                await scene.send(Message(LongMessageSegment(data={"id": str(res_id)})))

        elif text == ".test4":
            await scene.send(Message(OneBotDice()))

        elif text == ".test5":
            await scene.send(
                Message(
                    MusicSegment(
                        data={
                            "type": "custom",
                            "url": "https://harcicyang.github.io/schools",
                            "audio": "https://harcicyang.github.io/ctrl.m4a",
                            "title": "Test",
                        }
                    )
                )
            )

        elif text == ".test6":
            cookies = await self.api.raw("get_cookies", {"domain": "qun.qq.com"})
            print(cookies.data)

        elif text == ".test9":
            await scene.send(
                Message(
                    StreamSegment(data={"text": "ni shuo ni bu xiang zai zhe li wo ye bu xiang zai zhe li"}),
                    StreamSegment(data={"text": "wo ye bu xiang zai zhe li"}),
                    StreamSegment(data={"text": "dan tian hei de tai kuai xiang zou zao jiu lai bu ji"}),
                    StreamSegment(data={"text": "oh wo ai ni"}),
                    StreamSegment(data={"text": "ke xi guan xi bian cheng mei guan xi"}),
                    StreamSegment(data={"text": "wen ti shi mei wen ti"}),
                    StreamSegment(data={"text": "yu shi wo men ji xu"}),
                )
            )
