from Hyper import Manager, ModuleClass, Segments, WordSafety


class UserInfo:
    def __init__(self):
        self.inited = False
        self.violation_level: int = 1
        self.violations = 0
        self.last_message: str = ""
        self.last_time: int = 0
        self.words_unsafe_times = 0

    def inc_violations(self, num: int | float) -> None:
        self.violations += num

    def inc_unsafe_times(self) -> None:
        self.words_unsafe_times += 1

    def dec_unsafe_times(self) -> None:
        self.words_unsafe_times -= 1

    def clr_unsafe_times(self) -> None:
        self.words_unsafe_times = 0
        self.violation_level += 1

    def dec_violations(self, num: int | float) -> None:
        self.violations -= num

    def clr_violations(self) -> None:
        self.violations = 0
        self.violation_level += 1

    @property
    def need_mute(self) -> bool:
        return self.violations >= 12 or self.words_unsafe_times >= 3

    def update(self, last_msg, last_time) -> None:
        self.last_message = last_msg
        self.last_time = last_time
        self.inited = True


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


class InfoManager:
    def __init__(self):
        self.groups: dict[int, GroupInfo] = {}

    def get_group(self, gid: int) -> GroupInfo:
        if gid in self.groups:
            return self.groups[gid]
        else:
            self.groups[gid] = GroupInfo()
            return self.groups[gid]


data = InfoManager()


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
        user = data.get_group(self.event.group_id).get_user(self.event.user_id)
        if not user.inited:
            user.update(str(self.event.message), self.event.time)
            return

        sim = string_similarity(user.last_message, str(self.event.message))

        if self.event.time - user.last_time < 2:
            user.inc_violations(2)
        elif 2 < self.event.time - user.last_time < 20:
            user.inc_violations(1)
        elif 20 < self.event.time - user.last_time < 60:
            user.inc_violations(0.5)
        else:
            pass

        if sim < 0.66:
            pass
        elif 0.75 >= sim >= 0.66:
            user.inc_violations(1)
        elif 1 > sim >= 0.75:
            user.inc_violations(1.5)
        elif sim == 1:
            if len(self.event.message) == 1 and isinstance(self.event.message[0], Segments.Image):
                user.inc_violations(0.5)
            else:
                user.inc_violations(2)

        if len(str(self.event.message)) < 50:
            pass
        elif 100 > len(str(self.event.message)) >= 50:
            user.inc_violations(0.1)
        elif 150 > len(str(self.event.message)) >= 100:
            user.inc_violations(0.5)
        elif 200 > len(str(self.event.message)) >= 150:
            user.inc_violations(1)
        else:
            user.inc_violations(2)

        user.update(str(self.event.message), self.event.time)
        data.get_group(self.event.group_id).glb_dec()

        if user.need_mute:
            await self.actions.set_group_ban(user_id=self.event.user_id, group_id=self.event.group_id,
                                             duration=(60 * user.violation_level))
            await self.actions.send(user_id=self.event.user_id, group_id=self.event.group_id,
                                    message=Manager.Message(
                                        [
                                            Segments.At(str(self.event.user_id)),
                                            Segments.Text("请勿刷屏")
                                        ]
                                    )
                                    )
            user.clr_violations()
            user.inc_violations(2)

        safety = WordSafety.check(text=str(self.event.message))
        if not safety.result:
            await self.actions.del_message(self.event.message_id)
            await self.actions.send(user_id=self.event.user_id, group_id=self.event.group_id,
                                    message=Manager.Message(
                                        [
                                            Segments.At(str(self.event.user_id)),
                                            Segments.Text(safety.message)
                                        ]
                                    )
                                    )
            user.inc_unsafe_times()
            if user.need_mute:
                await self.actions.set_group_ban(user_id=self.event.user_id, group_id=self.event.group_id,
                                                 duration=(60 * user.violation_level))
                await self.actions.send(user_id=self.event.user_id, group_id=self.event.group_id,
                                        message=Manager.Message(
                                            [
                                                Segments.At(str(self.event.user_id)),
                                                Segments.Text("请勿发送违禁词")
                                            ]
                                        )
                                        )
                user.clr_unsafe_times()
