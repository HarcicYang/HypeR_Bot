from typing import Any

from hyperot import common, events, segments
from hyperot.events import GroupMessageEvent, PrivateMessageEvent
from typing_extensions import override

import ModuleClass

from .GuesserTools.shitchatter import silly_chatter

histories: dict[str, list[str]] = {}
msg_ids: list[str] = []


@ModuleClass.ModuleRegister.register(GroupMessageEvent, PrivateMessageEvent)
class Module(ModuleClass.Module[GroupMessageEvent | PrivateMessageEvent]):
    @override
    @staticmethod
    def info() -> ModuleClass.ModuleInfo:
        return ModuleClass.ModuleInfo(
            is_hidden=False,
            module_name="SillyChat",
            desc="基于模板的闲聊对话",
            helps="无显式命令。通过以下方式触发：\n- 在群聊中 @Bot\n- 引用 Bot 已发送的消息\n- 私聊发送 sb 开头的消息",
        )

    @staticmethod
    @override
    @staticmethod
    def filter(event: events.Event, allowed: list[Any]) -> bool:
        return (
            isinstance(event, PrivateMessageEvent)
            and len(event.message) != 0
            and str(event.message).startswith("sb")
            or (
                isinstance(event, GroupMessageEvent)
                and isinstance(event.message[0], segments.At)
                and event.message[0].qq == str(event.self_id)
            )
            or (
                isinstance(event, GroupMessageEvent)
                and isinstance(event.message[0], segments.Reply)
                and event.message[0].id in msg_ids
            )
        )

    @override
    async def handle(self):
        if histories.get(str(self.event.group_id)):
            history = histories[str(self.event.group_id)]
        else:
            histories[str(self.event.group_id)] = list()
            history = histories[str(self.event.group_id)]
        pure_msg = common.Message(segments.Text(""))
        for i in self.event.message:
            if not isinstance(i, segments.Text):
                continue
            pure_msg.add(i)
        text = str(pure_msg)
        reply = await silly_chatter(text, history)
        history.append(text)
        history.append(reply)
        # if str(self.event.group_id) == "367798007":
        #     reply = "- " + reply
        msg = await self.actions.send_msg(group_id=self.event.group_id, user_id=self.event.user_id, message=reply)
        msg_ids.append(str(msg.data.message_id))
