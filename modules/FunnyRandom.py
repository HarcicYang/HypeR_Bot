import asyncio
import dataclasses
import json
import os
import random
import time
from random import randint
from typing import Any, override

import httpx
from hyperot.common import Message
from hyperot.events import GroupMessageEvent, PrivateMessageEvent
from hyperot.segments import *

from ModuleClass import Module, ModuleInfo, ModuleRegister


@dataclasses.dataclass
class UserInfo:
    goodness: int
    time: int

    @property
    def level(self) -> str:
        if 0 <= self.goodness <= 20:
            return "像你这样的大人最讨厌了！"
        elif 20 < self.goodness <= 40:
            return "最差劲了"
        elif 40 < self.goodness <= 60:
            return "就那样吧"
        elif 60 < self.goodness <= 80:
            return "你真棒"
        else:
            return "👍_ _ _👍"

    @classmethod
    def build(cls) -> "UserInfo":
        return cls(randint(0, 100), int(time.time()))


users: dict[str, UserInfo] = {}


with open("./assets/quick.json", encoding="utf-8") as f:
    words = json.load(f)["ele"]


setu_last = int(time.time())
setu_cache = [f"file://{os.path.abspath('./assets/serika.png')}"]


@ModuleRegister.register(GroupMessageEvent, PrivateMessageEvent)
class Funny(Module[GroupMessageEvent | PrivateMessageEvent]):
    @override
    @staticmethod
    def info() -> ModuleInfo:
        return ModuleInfo(
            is_hidden=False,
            module_name="FunnyRandom",
            desc="趣味随机功能",
            helps="命令：\n今天有多棒 [@某人 / 我] - 查看今日评分\n发电 <目标名> - 生成随机发电小作文",
        )

    @override
    async def handle(self):
        global setu_last
        if "今天有多棒" in str(self.event.message):
            if "我" in str(self.event.message):
                name = "\n你"
                uin = str(self.event.user_id)
            elif "@" in str(self.event.message):
                name = ""
                uin = self.event.message[0].qq
            else:
                return

            if str(uin) not in users:
                users[str(uin)] = UserInfo.build()
            msg = Message(At(uin), Text(f"{name}今天的分数: {users[str(uin)].goodness}\n评级: {users[str(uin)].level}"))
            await self.actions.send_msg(group_id=self.event.group_id, user_id=self.event.user_id, message=msg)
        elif str(self.event.message) == "随机色图":
            if int(time.time()) - setu_last <= 15:
                await self.actions.send_msg(
                    group_id=self.event.group_id, user_id=self.event.user_id, message=Message(Text("调用过于频繁"))
                )
                return

            setu_last = int(time.time())

            url = "https://image.anosu.top/pixiv/json"
            tags = [
                "原神",
                "崩坏",
                "蔚蓝档案",
                "水着",
                "萝莉",
                "猫娘",
                "明日方舟",
                "绯染天空",
                "None1",
                "None2",
                "None3",
                "None4",
                "None5",
            ]
            tag = random.choice(tags)
            if "None" in tag:
                pass
            else:
                url += f"?keyword={tag}"
            retried = 0
            response: list[Any] = []
            while retried <= 5:
                response = httpx.get(url).json()
                if response == list():
                    await asyncio.sleep(5)
                    retried += 1
                    continue
                else:
                    break

            if len(response) == 0:
                url = random.choice(setu_cache)
            else:
                url = response[0]["url"]
                setu_cache.append(url)

            await self.actions.send_msg(
                group_id=self.event.group_id, user_id=self.event.user_id, message=Message(Image(url))
            )
        elif str(self.event.message).startswith("发电 "):
            tag = str(self.event.message).replace("发电 ", "", 1)
            word = random.choice(words).replace("{target_name}", tag)
            await self.actions.send_msg(
                group_id=self.event.group_id,
                user_id=self.event.user_id,
                message=Message(Reply(self.event.message_id), Text(word)),
            )
