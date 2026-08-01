import json
import random
from typing import override

from hyperot import common, segments
from hyperot.events import *

import ModuleClass

with open("./assets/quick.json", encoding="utf-8") as f:
    quicks = json.load(f)

cache: dict[str, list[str | None]] = {}


@ModuleClass.ModuleRegister.register(
    GroupAddInviteEvent, GroupMemberDecreaseEvent, GroupMemberIncreaseEvent, GroupMessageEvent
)
class Module(
    ModuleClass.Module[GroupAddInviteEvent | GroupMemberDecreaseEvent | GroupMemberIncreaseEvent | GroupMessageEvent]
):
    @override
    @staticmethod
    def info() -> ModuleClass.ModuleInfo:
        return ModuleClass.ModuleInfo(
            is_hidden=False,
            module_name="Welcome",
            desc="入群欢迎、退群欢送、加群请求管理",
            helps="自动回复：\n- 新成员入群：随机欢迎消息\n- 成员退群：随机欢送消息\n- 加群请求：自动审批\n- 回复加群请求消息发送 .comment 可查看验证消息\n- 回复加群请求消息发送 .approve 可通过该请求",
        )

    @override
    async def handle(self):
        if self.event.blocked or self.event.is_silent:
            return
        if self.event.user_id is None or self.event.group_id is None:
            return
        if isinstance(self.event, NoticeEvent):
            if isinstance(self.event, GroupMemberIncreaseEvent):
                text = str(random.choice(quicks["group_increase"])).split("<user>")
                await self.actions.send_msg(
                    group_id=self.event.group_id,
                    message=common.Message(
                        [segments.Text(text[0]), segments.At(str(self.event.user_id)), segments.Text(text[1])]
                    ),
                )
            elif isinstance(self.event, GroupMemberDecreaseEvent):
                try:
                    user_info = await self.actions.get_stranger_info(user_id=self.event.user_id)
                    text = str(random.choice(quicks["group_decrease"][self.event.sub_type])).replace(
                        "<user>", f"{user_info.data.nickname}({self.event.user_id})"
                    )
                    await self.actions.send_msg(
                        group_id=self.event.group_id, message=common.Message([segments.Text(text)])
                    )

                except KeyError:
                    return None
            else:
                return None

        elif isinstance(self.event, RequestEvent) and isinstance(self.event, GroupAddInviteEvent):
            if self.event.sub_type == "add":
                # await self.actions.set_group_add_request(flag=self.event.flag, sub_type=self.event.sub_type,
                #                                          approve=True)
                # await self.actions.send_msg(group_id=self.event.group_id, message=Comm.Message(
                #     [
                #         Segments.Text("同意用户"), Segments.At(self.event.user_id), Segments.Text("的加群请求。"),
                #         Segments.Text("\n"),
                #         Segments.Text(str(self.event.comment))
                #     ]
                # ))
                uinfo = await self.actions.get_stranger_info(self.event.user_id)
                msg = await self.actions.send_msg(
                    group_id=self.event.group_id,
                    message=common.Message(
                        [
                            segments.Text(
                                f"有新的入群请求，来自用户 {uinfo.data.nickname}（QQ {self.event.user_id}），请尽快处理"
                            )
                        ]
                    ),
                )
                cache[str(msg.data.message_id)] = [self.event.comment, self.event.flag]
            # elif self.event.sub_type == "invite":
            #     message = common.Message(
            #         [
            #             segments.Text(f"HypeR Bot 通过用户 QQ {self.event.user_id}的邀请加入群组")
            #         ]
            #     )
            #     await self.actions.send_msg(group_id=self.event.group_id, message=message)
        elif isinstance(self.event, GroupMessageEvent):
            _id = None
            for i in self.event.message:
                if isinstance(i, segments.Reply):
                    _id = i.id
                    break
            if _id and _id in cache:
                comment, flag = cache[_id]
                if ".comment" in str(self.event.message):
                    if comment is None:
                        return
                    await self.actions.send_msg(
                        group_id=self.event.group_id,
                        user_id=self.event.user_id,
                        message=common.Message(segments.Reply(self.event.message_id), segments.Text(comment)),
                    )
                elif ".approve" in str(self.event.message):
                    if flag is None:
                        return
                    await self.actions.set_group_add_request(flag=flag, sub_type="add", approve=True)
