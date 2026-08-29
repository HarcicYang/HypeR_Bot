import json
import os
import random
import traceback

from hyperot import common, hyperogger, segments
from hyperot.events import *
from typing_extensions import override

import ModuleClass

with open("./assets/quick.json", encoding="utf-8") as f:
    quicks = json.load(f)

_logger = hyperogger.Logger()


def _cache_path() -> str:
    return "./temps/welcome_requests.json"


def _load_cache() -> dict[str, list[str | None]]:
    """磁盘懒加载;损坏时备份原文件后重置为空。"""
    try:
        with open(_cache_path(), encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except FileNotFoundError:
        pass
    except (OSError, json.JSONDecodeError):
        _logger.warning("加群请求缓存损坏: " + traceback.format_exc())
        try:
            if os.path.exists(_cache_path()):
                os.replace(_cache_path(), _cache_path() + ".bak")
        except OSError:
            pass
    return {}


def _save_cache(cache: dict[str, list[str | None]]) -> None:
    os.makedirs(os.path.dirname(_cache_path()) or ".", exist_ok=True)
    tmp = _cache_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _cache_path())


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
                cache = _load_cache()
                cache[str(msg.data.message_id)] = [self.event.comment, self.event.flag]
                _save_cache(cache)
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
            if _id is not None:
                cache = _load_cache()
                if _id not in cache:
                    return
            else:
                return
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
                cache = _load_cache()
                del cache[_id]
                _save_cache(cache)
