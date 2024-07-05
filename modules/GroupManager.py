import os.path
import json

from Hyper import Manager, ModuleClass, Segments, WordSafety


class UserInfo:
    def __init__(self):
        self.inited = False
        self.violation_level: int = 1
        self.violations = 0
        self.last_message: str = ""
        self.last_time: int = 0
        self.words_unsafe_times = 0
        self.k1 = 1
        self.k2 = 1

    def inc_violations(self, num: int | float) -> None:
        self.violations += (num * self.k1)

    def inc_unsafe_times(self) -> None:
        self.words_unsafe_times += 1

    def dec_unsafe_times(self) -> None:
        self.words_unsafe_times -= 1

    def clr_unsafe_times(self) -> None:
        self.words_unsafe_times = 0
        self.violation_level += 1

    def dec_violations(self, num: int | float) -> None:
        self.violations -= num
        if self.violations <= 0:
            self.violations = 0

    def clr_violations(self) -> None:
        self.violations = 0
        self.violation_level += 1

    @property
    def need_mute(self) -> bool:
        return self.violations >= (6.5 * self.k2) or self.words_unsafe_times >= 3

    def update(self, last_msg, last_time) -> None:
        self.last_message = last_msg
        self.last_time = last_time
        self.inited = True

    def set_k(self, k1: float, k2: float) -> None:
        self.k1 = k1 + (self.violation_level * 0.000001)
        self.k2 = k2

    @classmethod
    def load(cls, j_data: dict) -> "UserInfo":
        obj = cls()
        obj.inited = True
        obj.violation_level = j_data["violation_level"]
        obj.violations = j_data["violations"]
        obj.last_message = j_data["last_message"]
        obj.last_time = j_data["last_time"]
        obj.words_unsafe_times = j_data["words_unsafe_times"]

        return obj

    def dump(self) -> dict:
        return dict(
            violation_level=self.violation_level,
            violations=self.violations,
            last_message=self.last_message,
            last_time=self.last_time,
            words_unsafe_times=self.words_unsafe_times,
        )


class GroupInfo:
    def __init__(self):
        self.users: dict[int, UserInfo] = {}

    def get_user(self, uin: int) -> UserInfo:
        if uin in self.users:
            return self.users[uin]
        else:
            self.users[uin] = UserInfo()
            return self.users[uin]

    def glb_dec(self) -> None:
        for i in self.users:
            self.users[i].dec_violations(1)

    @classmethod
    def load(cls, j_data: dict) -> "GroupInfo":
        obj = cls()
        dic = dict()
        for i in j_data:
            dic[int(i)] = UserInfo.load(j_data[i])
        obj.users = dic

        return obj

    def dump(self) -> dict:
        dic = dict()
        for i in self.users:
            dic[str(i)] = self.users[i].dump()

        return dic

    def gen_k(self) -> None:
        x = len(self.users)
        y1 = (0.0005 * x) + 1
        y2 = (0.000001 * (x ** 2)) + 1
        if y1 >= y2:
            k1 = y1
            k2 = y2
        else:
            k1 = y2
            k2 = y1

        for i in self.users:
            self.users[i].set_k(k1, k2)


class InfoManager:
    def __init__(self):
        self.groups: dict[int, GroupInfo] = {}

    def get_group(self, gid: int) -> GroupInfo:
        if gid in self.groups:
            return self.groups[gid]
        else:
            self.groups[gid] = GroupInfo()
            return self.groups[gid]

    @classmethod
    def load(cls, j_data: dict) -> "InfoManager":
        obj = cls()
        dic = dict()
        for i in j_data:
            dic[int(i)] = GroupInfo.load(j_data[i])
        obj.groups = dic

        return obj

    @classmethod
    def load_from(cls, path: str) -> "InfoManager":
        if os.path.exists(path):
            with open(path, "r") as f:
                j_data = json.load(f)
            return cls.load(j_data)
        else:
            return cls()

    def dump(self) -> dict:
        dic = dict()
        for i in self.groups:
            dic[str(i)] = self.groups[i].dump()

        return dic

    def dump_to(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.dump(), f, indent=2)


data = InfoManager.load_from("group.json")


def distance(s1: str, s2: str) -> int:
    if s2 > s1:
        s1, s2 = s2, s1

    difference = 0
    s2 += " " * (len(s1) - len(s2))
    for i in range(len(s1)):
        if s1[i] != s2[i]:
            difference += 1

    return difference


def string_similarity(s1: str, s2: str) -> float:
    try:
        similarity = 1 - distance(s1, s2) / max(len(s1), len(s2))
    except:
        return 1.0
    return similarity


@ModuleClass.ModuleRegister.register(["message"])
class Module(ModuleClass.Module):
    async def handle(self):
        if self.event.is_owner and str(self.event.message) == ".dump":
            print(data.dump())

        user = data.get_group(self.event.group_id).get_user(self.event.user_id)
        if not user.inited:
            user.update(str(self.event.message), self.event.time)
            return

        data.get_group(self.event.group_id).gen_k()

        sim = string_similarity(user.last_message, str(self.event.message))

        if self.event.time - user.last_time < 2:
            user.inc_violations(2)
        elif 2 < self.event.time - user.last_time < 10:
            user.inc_violations(1)
        elif 10 < self.event.time - user.last_time < 20:
            user.inc_violations(0.2)
        else:
            pass

        if sim < 0.66:
            pass
        elif 0.75 >= sim >= 0.66:
            user.inc_violations(0.5)
        elif 1 > sim >= 0.75:
            user.inc_violations(1)
        elif sim == 1:
            if str(self.event.message) == "[图片]":
                user.inc_violations(0.5)
            else:
                user.inc_violations(2)

        if len(str(self.event.message)) < 50:
            pass
        elif 100 > len(str(self.event.message)) >= 50:
            user.inc_violations(0.2)
        elif 150 > len(str(self.event.message)) >= 100:
            user.inc_violations(1)
        elif 200 > len(str(self.event.message)) >= 150:
            user.inc_violations(2)
        else:
            user.inc_violations(3)

        user.update(str(self.event.message), self.event.time)
        data.get_group(self.event.group_id).glb_dec()

        if user.need_mute:
            await self.actions.set_group_ban(user_id=self.event.user_id, group_id=self.event.group_id,
                                             duration=(120 * user.violation_level))
            # await self.actions.send(user_id=self.event.user_id, group_id=self.event.group_id,
            #                         message=Manager.Message(
            #                             [
            #                                 Segments.At(str(self.event.user_id)),
            #                                 Segments.Text("请勿刷屏")
            #                             ]
            #                         )
            #                         )
            user.clr_violations()
            user.inc_violations(2)

        safety = WordSafety.check(text=str(self.event.message))
        if not safety.result:
            await self.actions.del_message(self.event.message_id)
            # await self.actions.send(user_id=self.event.user_id, group_id=self.event.group_id,
            #                         message=Manager.Message(
            #                             [
            #                                 Segments.At(str(self.event.user_id)),
            #                                 Segments.Text(safety.message)
            #                             ]
            #                         )
            #                         )
            user.inc_unsafe_times()
            if user.need_mute:
                await self.actions.set_group_ban(user_id=self.event.user_id, group_id=self.event.group_id,
                                                 duration=(120 * user.violation_level))
                await self.actions.send(user_id=self.event.user_id, group_id=self.event.group_id,
                                        message=Manager.Message(
                                            [
                                                Segments.At(str(self.event.user_id)),
                                                Segments.Text("请勿发送违禁词")
                                            ]
                                        )
                                        )
                user.clr_unsafe_times()

        data.dump_to("group.json")
