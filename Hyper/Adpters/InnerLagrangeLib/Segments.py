import asyncio
import json
from Hyper.Errors import *
from lagrange.client.message import elems
from Hyper.Adpters.InnerLagrangeLib import LagrangeClient


async def get_uid(gid: int, uin: int) -> str:
    r = await LagrangeClient.client.get_grp_members(grp_id=int(gid))
    for i in r.body:
        if i.account.uin == uin:
            return i.account.uid
    return "0"


class Text:
    def __init__(self, text: str):
        self.content = elems.Text(text)

    def set(self, text: str) -> None:
        self.__init__(text)

    def get(self) -> str:
        return str(self.content)

    async def get_raw(self, **kwargs) -> elems.Text:
        return self.content

    def __str__(self) -> str:
        return self.content.text

    def __repr__(self) -> str:
        return self.get()


class Image:
    def __init__(self, image: str, summary: str = "[图片]"):
        self.content = {"type": "image", "data": {"file": image, "summary": summary}}

    def set(self, image: str, summary: str = "[图片]") -> None:
        self.__init__(image, summary)

    def get(self) -> str:
        return self.content["data"]["file"]

    async def get_raw(self, **kwargs) -> elems.Image:
        if kwargs.get("group_id") is not None:
            return await LagrangeClient.client.upload_grp_image(
                open(self.content["data"]["file"].replace("file://", ""), "rb"), kwargs["group_id"]
            )
        else:
            return await LagrangeClient.client.upload_friend_image(
                open(self.content["data"]["file"].replace("file://", ""), "rb"), kwargs["user_id"]
            )

    def __str__(self) -> str:
        return self.content["data"]["summary"]

    def __repr__(self) -> str:
        return str(self.content)


class At:
    def __init__(self, user_id: str):
        self.content = {"type": "at", "data": {"qq": str(user_id)}}

    def set(self, user_id: str) -> None:
        self.__init__(user_id)

    def get(self) -> str:
        return self.content["data"]["qq"]

    async def get_raw(self, **kwargs) -> elems.At | elems.AtAll:
        if self.content["data"]["qq"] == "all":
            return elems.AtAll(text="@全体成员 ")
        else:
            uid = await get_uid(kwargs["group_id"], int(self.content["data"]["qq"]))
            name = (await LagrangeClient.client.get_user_info(uid)).name
            return elems.At(uid=uid, uin=int(self.content["data"]["qq"]), text=f"@{name} ")

    def __str__(self) -> str:
        return f"@{self.content['data']['qq']} "

    def __repr__(self) -> str:
        return str(self.content)


class Reply:
    def __init__(self, message_id: str):
        self.content = elems.Quote.build(LagrangeClient.msg_history[int(message_id)])

    def set(self, message_id: str) -> None:
        self.__init__(message_id)

    def get(self) -> str:
        return str(self.content)

    async def get_raw(self, **kwargs) -> elems.Quote:
        return self.content

    def __str__(self) -> str:
        return "[回复]"

    def __repr__(self) -> str:
        return str(self.content)


class Face:
    def __init__(self, face_id: str):
        self.content = {"type": "face", "data": {"id": face_id}}

    def set(self, face_id: str) -> None:
        self.__init__(face_id)

    def get(self) -> str:
        return self.content["data"]["id"]

    async def get_raw(self, **kwargs) -> dict:
        return self.content

    def __str__(self) -> str:
        return "[表情]"

    def __repr__(self) -> str:
        return str(self.content)


class Video:
    def __init__(self, video: str):
        self.content = {"type": "video", "data": {"file": video}}

    def set(self, video: str) -> None:
        self.__init__(video)

    def get(self) -> str:
        return self.content["data"]["file"]

    async def get_raw(self, **kwargs) -> dict:
        return self.content

    def __str__(self) -> str:
        return "[视频]"

    def __repr__(self) -> str:
        return str(self.content)


class Poke:
    def __init__(self, poke_type: str, poke_id: str):
        self.content = {"type": "poke", "data": {"type": poke_type, "id": poke_id}}

    def set(self, poke_type: str, poke_id: str) -> None:
        self.__init__(poke_type, poke_id)

    def get(self) -> None:
        raise NotSupportError("This type of message cannot use '.get()'")

    async def get_raw(self, **kwargs) -> dict:
        return self.content

    def __str__(self) -> str:
        return "[戳一戳]"

    def __repr__(self) -> str:
        return str(self.content)


class Json:
    def __init__(self, content: dict):
        self.content = {"type": "json", "data": {"data": json.dumps(content, ensure_ascii=False).replace("'", r'/"')}}

    def set(self, content: dict) -> None:
        self.__init__(content)

    def get(self) -> dict:
        return json.loads(self.content["data"]["data"])

    async def get_raw(self, **kwargs) -> dict:
        return self.content

    def __str__(self) -> str:
        return f"[Json]"

    def __repr__(self) -> str:
        return str(self.content)


class MarketFace:
    def __init__(self, face_id: str, tab_id: str, key: str):
        self.content = {"type": "marketface", "data": {"face_id": face_id, "tab_id": tab_id, "key": key}}

    def set(self, face_id: str, tab_id: str, key: str) -> None:
        self.__init__(face_id, tab_id, key)

    def get(self) -> str:
        return self.content["data"]["face_id"]

    async def get_raw(self, **kwargs) -> dict:
        return self.content

    def __str__(self) -> str:
        return ""

    def __repr__(self) -> str:
        return str(self.content)


class Types:
    def __contains__(self, item):
        for i in [elems.Text, elems.Image, elems.At, elems.Quote]:
            if isinstance(item, i):
                return True

        return False

    def __getitem__(self, item):
        if isinstance(item, elems.Quote):
            return {
                "type": Reply,
                "args": [
                    "id"
                ]
            }
        if isinstance(item, elems.Image):
            return {
                "type": Image,
                "args": [
                    "url",
                    "text"
                ]
            }
        if isinstance(item, elems.At):
            return {
                "type": At,
                "args": [
                    "qq"
                ]
            }
        if isinstance(item, elems.Text):
            return {
                "type": Text,
                "args": [
                    "text"
                ]
            }


message_types = Types()

# message_types = {
#     elems.Text: {
#         "type": Text,
#         "args": [
#             "text"
#         ]
#     },
#     elems.Image: {
#         "type": Image,
#         "args": [
#             "file"
#         ]
#     },
#     elems.At: {
#         "type": At,
#         "args": [
#             "qq"
#         ]
#     },
#     elems.Quote: {
#         "type": Reply,
#         "args": [
#             "id"
#         ]
#     },
#     "face": {
#         "type": Face,
#         "args": [
#             "id"
#         ]
#     },
#     "video": {
#         "type": Video,
#         "args": [
#             "file"
#         ]
#     },
#     "poke": {
#         "type": Poke,
#         "args": [
#             "type",
#             "id"
#         ]
#     },
#     "marketface": {
#         "type": MarketFace,
#         "args": [
#             "face_id",
#             "tab_id",
#             "key"
#         ]
#     }
# }
