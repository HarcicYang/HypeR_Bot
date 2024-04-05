from Hyper import Manager, ModuleClass, Segments, WordSafety
from Levenshtein import distance


class UserInfo:
    def __init__(self):
        self.violation_level: int = 1
        self.violations = 0
        self.last_message: str = ""
        self.last_time: int = 0
        self.words_unsafe_times = 0


data: dict[int, UserInfo] = {}


def string_similarity(s1: str, s2: str) -> float:
    try:
        similarity = 1 - distance(s1, s2) / max(len(s1), len(s2))
    except:
        return 1.0
    return similarity


@ModuleClass.ModuleRegister.register(["message"])
class Module(ModuleClass.Module):
    async def handle(self):
        if not data.get(self.event.user_id):
            data[self.event.user_id] = UserInfo()
            try:
                data[self.event.user_id].last_message = str(self.event.message)
            except AttributeError:
                return None
            data[self.event.user_id].last_time = self.event.time
            return None

        if string_similarity(data[self.event.user_id].last_message, str(self.event.message)) >= 0.66\
                or len(str(self.event.message)) >= 120\
                or self.event.time - data[self.event.user_id].last_time < 2:
            if self.event.time - data[self.event.user_id].last_time < 2:
                data[self.event.user_id].violations += 2
            elif 2 < self.event.time - data[self.event.user_id].last_time < 20:
                data[self.event.user_id].violations += 1
            elif 20 < self.event.time - data[self.event.user_id].last_time < 60:
                data[self.event.user_id].violations += 0.5
            else:
                data[self.event.user_id].violations += 0.1

        data[self.event.user_id].last_message = str(self.event.message)
        data[self.event.user_id].last_time = self.event.time

        for i in data:
            data[i].violations -= 1 if i != self.event.user_id else 0
            if data[i].violations < 0:
                data[i].violations = 0

        if data[self.event.user_id].violations >= 5:
            self.actions.set_group_ban(user_id=self.event.user_id, group_id=self.event.group_id,
                                       duration=(60 * data[self.event.user_id].violation_level))
            self.actions.send(user_id=self.event.user_id, group_id=self.event.group_id,
                              message=Manager.Message(
                                  [
                                      Segments.At(str(self.event.user_id)),
                                      Segments.Text("请勿刷屏")
                                  ]
                              )
                              )
            data[self.event.user_id].violations = 2
            data[self.event.user_id].violation_level += 1

        safety = WordSafety.check(text=str(self.event.message))
        if not safety.result:
            self.actions.del_message(self.event.message_id)
            self.actions.send(user_id=self.event.user_id, group_id=self.event.group_id,
                              message=Manager.Message(
                                  [
                                      Segments.At(str(self.event.user_id)),
                                      Segments.Text(safety.message)
                                  ]
                              )
                              )
            data[self.event.user_id].words_unsafe_times += 1
            if data[self.event.user_id].words_unsafe_times >= 3:
                self.actions.set_group_ban(user_id=self.event.user_id, group_id=self.event.group_id,
                                           duration=(60 * data[self.event.user_id].violation_level))
                self.actions.send(user_id=self.event.user_id, group_id=self.event.group_id,
                                  message=Manager.Message(
                                      [
                                          Segments.At(str(self.event.user_id)),
                                          Segments.Text("请勿发送违禁词")
                                      ]
                                  )
                                  )
                data[self.event.user_id].words_unsafe_times = 0
                data[self.event.user_id].violation_level += 1
