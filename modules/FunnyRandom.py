import asyncio
import os.path
import random
import time
import httpx
import matplotlib.pyplot as plt
import numpy as np
from random import randint
from matplotlib.patches import Arc
import dataclasses
import json

from Hyper.Manager import Message
from Hyper.Segments import *
from ModuleClass import ModuleRegister, Module
from Hyper.Events import GroupMessageEvent, PrivateMessageEvent


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
            return "👍校溯酥👍"

    @classmethod
    def build(cls) -> "UserInfo":
        return cls(randint(0, 100), int(time.time()))


users: dict[str, UserInfo] = {}


with open("./assets/quick.json", "r", encoding="utf-8") as f:
    words = json.load(f)["ele"]


def plot_angle(angle_degrees, path):
    plt.clf()
    angle_radians = np.deg2rad(angle_degrees)
    line_length = 2

    x1 = [0, line_length * np.cos(np.deg2rad(0))]
    y1 = [0, line_length * np.sin(np.deg2rad(0))]
    x2 = [0, line_length * np.cos(angle_radians)]
    y2 = [0, line_length * np.sin(angle_radians)]

    plt.plot(x1, y1, "b-", linewidth=3.5)
    plt.plot(x2, y2, "b-", linewidth=3.5)

    arc = Arc((0, 0), width=2 * line_length, height=2 * line_length,
              theta1=np.deg2rad(0), theta2=angle_radians,
              linewidth=2, linestyle="--", color="r")

    plt.gca().add_patch(arc)

    plt.gca().set_aspect("equal", adjustable="box")

    plt.xlim(-1.5, 1.5)
    plt.ylim(-1.5, 1.5)
    plt.axis("off")
    plt.title(f"Random angle: {angle_degrees}°")
    plt.savefig(path)


setu_last = int(time.time())
setu_cache = [f"file://{os.path.abspath('./assets/serika.png')}"]


@ModuleRegister.register(GroupMessageEvent, PrivateMessageEvent)
class Funny(Module):
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

            if str(uin) not in users.keys():
                users[str(uin)] = UserInfo.build()
            msg = Message(
                At(uin),
                Text(
                    f"{name}今天的分数: {users[str(uin)].goodness}\n评级: {users[str(uin)].level}")
            )
            await self.actions.send(
                group_id=self.event.group_id,
                user_id=self.event.user_id,
                message=msg
            )
        elif str(self.event.message) == "随机色图":
            if int(time.time()) - setu_last <= 15:
                await self.actions.send(
                    group_id=self.event.group_id,
                    user_id=self.event.user_id,
                    message=Message(Text("调用过于频繁"))
                )
                return

            setu_last = int(time.time())

            url = "https://image.anosu.top/pixiv/json"
            tags = ["原神", "崩坏", "蔚蓝档案", "水着", "萝莉", "猫娘", "明日方舟",
                    "绯染天空", "None1", "None2", "None3", "None4", "None5"]
            tag = random.choice(tags)
            if "None" in tag:
                pass
            else:
                url += f"?keyword={tag}"
            retried = 0
            response = []
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

            await self.actions.send(
                group_id=self.event.group_id,
                user_id=self.event.user_id,
                message=Message(
                    Image(url)
                )
            )
        elif str(self.event.message).startswith("发电"):
            tag = str(self.event.message).replace("发电 ", "", 1)
            word = random.choice(words).replace("{target_name}", tag)
            await self.actions.send(
                group_id=self.event.group_id,
                user_id=self.event.user_id,
                message=Message(
                    Reply(self.event.message_id), Text(word)
                )
            )

