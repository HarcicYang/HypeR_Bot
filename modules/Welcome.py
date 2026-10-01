import json
import os
import random
import traceback

from hyperot import hyperogger
from hyperot.v2 import Mention, Message, Quote, Text
from hyperot.v2.events import (
    GroupJoinRequestedEvent,
    MemberJoinedEvent,
    MemberLeftEvent,
    MessageReceivedEvent,
)
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


@ModuleClass.ModuleRegister.register(GroupJoinRequestedEvent, MemberJoinedEvent, MemberLeftEvent, MessageReceivedEvent)
class Module(ModuleClass.Module[GroupJoinRequestedEvent | MemberJoinedEvent | MemberLeftEvent | MessageReceivedEvent]):
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
        gid = str(self.event.scene_id)
        if isinstance(self.event, MemberJoinedEvent):
            text = str(random.choice(quicks["group_increase"])).split("<user>")
            await self.api.group(gid).send(
                Message(Text(text=text[0]), Mention(user_id=str(self.event.member_id)), Text(text=text[1]))
            )
        elif isinstance(self.event, MemberLeftEvent):
            try:
                user_info = await self.api.user(str(self.event.member_id)).profile()
                sub_type = "kick" if self.event.kicked else "leave"
                text = str(random.choice(quicks["group_decrease"][sub_type])).replace(
                    "<user>", f"{user_info.display_name or '未知用户'}({self.event.member_id})"
                )
                await self.api.group(gid).send(Message(Text(text=text)))
            except KeyError:
                return None
        elif isinstance(self.event, GroupJoinRequestedEvent):
            uinfo = await self.api.user(str(self.event.user_id)).profile()
            msg = await self.api.group(gid).send(
                Message(
                    Text(
                        text=f"有新的入群请求，来自用户 {uinfo.display_name or '未知用户'}（QQ {self.event.user_id}），请尽快处理"
                    )
                )
            )
            cache = _load_cache()
            cache[str(msg.message_id)] = [self.event.comment, str(self.event.request_id)]
            _save_cache(cache)
        elif isinstance(self.event, MessageReceivedEvent):
            _id = None
            for i in self.event.message:
                if isinstance(i, Quote):
                    _id = str(i.message_id)
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
                await self.api.scene(self.event.scene_type, self.event.scene_id).send(
                    Message(Quote(message_id=str(self.event.message_id)), Text(text=comment))
                )
            elif ".approve" in str(self.event.message):
                if flag is None:
                    return
                await self.api.group_request(flag).approve()
                cache = _load_cache()
                del cache[_id]
                _save_cache(cache)
