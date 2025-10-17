from ..utils.hypetyping import Literal


class OneBotEventBuilder:
    def __init__(self, time: int, self_id: int, user_id: int, group_id: int):
        self.data = {
            "time": time,
            "self_id": self_id,
            "user_id": user_id,
            "group_id": group_id
        }

    def _as_message(self, message: list, message_id: str) -> "OneBotEventBuilder":
        self.data["post_type"] = "message"
        self.data["message"] = message
        self.data["message_id"] = message_id
        return self

    def as_group_message(self, message: list, message_id: str, sub_type: str = "normal") -> "OneBotEventBuilder":
        self.data["message_type"] = "group"
        self.data["sub_type"] = sub_type
        return self._as_message(message, message_id)

    def as_private_message(self, message: list, message_id: str, sub_type: str = "friend") -> "OneBotEventBuilder":
        self.data["message_type"] = "private"
        self.data["sub_type"] = sub_type
        return self._as_message(message, message_id)

    def group_sender(self, nickname: str, sex: str, age: int, card: str, area: str, level: str, role: str, title: str) -> "OneBotEventBuilder":
        self.data["sender"] = {
            "user_id": self.data.get("user_id"),
            "nickname": nickname,
            "sex": sex,
            "age": age,
            "card": card,
            "area": area,
            "level": level,
            "role": role,
            "title": title
        }
        return self

    def private_sender(self, nickname: str, sex: str, age: int) -> "OneBotEventBuilder":
        self.data["sender"] = {
            "user_id": self.data.get("user_id"),
            "nickname": nickname,
            "sex": sex,
            "age": age
        }
        return self

    def _as_notice(self) -> "OneBotEventBuilder":
        self.data["post_type"] = "notice"
        return self

    def as_group_file_upload(self, file: dict) -> "OneBotEventBuilder":
        self.data["notice_type"] = "group_upload"
        self.data["file"] = file
        return self._as_notice()

    def as_group_admin_event(self):
        self.data["notice_type"] = "group_admin"
        return self._as_notice()

    def as_group_decrease_event(self, operator_id: int, sub_type: str = "leave") -> "OneBotEventBuilder":
        self.data["notice_type"] = "group_decrease"
        self.data["operator_id"] = operator_id
        self.data["sub_type"] = sub_type
        return self._as_notice()

    def as_group_increase_event(self, operator_id: int, sub_type: str = "approve") -> "OneBotEventBuilder":
        self.data["notice_type"] = "group_increase"
        self.data["operator_id"] = operator_id
        self.data["sub_type"] = sub_type
        return self._as_notice()

    def as_group_mute_event(self, operator_id: int, duration: int, sub_type: str = "ban") -> "OneBotEventBuilder":
        self.data["notice_type"] = "group_ban"
        self.data["operator_id"] = operator_id
        self.data["duration"] = duration
        self.data["sub_type"] = sub_type
        return self._as_notice()

    def as_friend_add_event(self) -> "OneBotEventBuilder":
        self.data["notice_type"] = "friend_add"
        return self._as_notice()

    def as_group_recall_event(self, operator_id: int, message_id: str) -> "OneBotEventBuilder":
        self.data["notice_type"] = "group_recall"
        self.data["operator_id"] = operator_id
        self.data["message_id"] = message_id
        return self._as_notice()

    def as_private_recall_event(self, message_id: str) -> "OneBotEventBuilder":
        self.data["notice_type"] = "private_recall"
        self.data["message_id"] = message_id
        return self._as_notice()

    def _as_notify(self, notify_type: Literal["poke", "lucky_king", "honor"]) -> "OneBotEventBuilder":
        self.data["post_type"] = "notify"
        self.data["notify_type"] = notify_type
        return self._as_notice()

    def as_poke(self) -> "OneBotEventBuilder":
        self.data["sub_type"] = "poke"
        return self._as_notify("poke")

    def as_lucky(self) -> "OneBotEventBuilder":
        self.data["sub_type"] = "lucky_king"
        return self._as_notify("lucky_king")

    def as_honor(self, honor_type: str) -> "OneBotEventBuilder":
        self.data["sub_type"] = "honor"
        self.data["honor_type"] = honor_type
        return self._as_notify("honor")

    def as_group_essence_event(self, sender_id: int, operator_id: int,  message_id: str) -> "OneBotEventBuilder":
        self.data["notice_type"] = "essence"
        self.data["sender_id"] = sender_id
        self.data["operator_id"] = operator_id
        self.data["message_id"] = message_id
        return self._as_notice()

    def as_group_reaction_event(self, message_id: str, operator_id: int, code: int, count: int) -> "OneBotEventBuilder":
        self.data["notice_type"] = "reaction"
        self.data["message_id"] = message_id
        self.data["operator_id"] = operator_id
        self.data["code"] = code
        self.data["count"] = count
        return self._as_notice()

    def as_bot_online_event(self, reason: str) -> "OneBotEventBuilder":
        self.data["notice_type"] = "bot_online"
        self.data["reason"] = reason
        return self

    def _as_request(self, comment: str, flag: str) -> "OneBotEventBuilder":
        self.data["post_type"] = "request"
        self.data["comment"] = comment
        self.data["flag"] = flag
        return self

    def as_friend_add_request(self, comment: str, flag: str) -> "OneBotEventBuilder":
        self.data["request_type"] = "friend"
        return self._as_request(comment, flag)

    def as_group_add_request(self, comment: str, flag: str, sub_type: str = "add") -> "OneBotEventBuilder":
        self.data["request_type"] = "group"
        self.data["sub_type"] = sub_type
        return self._as_request(comment, flag)

    def build(self) -> dict:
        return self.data
