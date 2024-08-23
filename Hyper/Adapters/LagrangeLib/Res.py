import random
from typing import Union
import base64
import httpx
from lagrange.client.client import Client as LgrCli
from lagrange.client.events.friend import FriendMessage
from lagrange.client.message import elems
from lagrange.client.events.group import (
    GroupMessage,
    GroupRecall,
    GroupMuteMember,
    GroupMemberJoined,
    GroupMemberQuit,
    GroupReaction
)

from Hyper.Adapters.LagrangeLib.LagrangeClient import lgr, uc, config, event_queue

message_types = {}


def segment_builder(sg_type: str, summary_tmp: str = None):
    # print(inspect.get_annotations(cls))
    def inner_builder(cls):
        var = dict(vars(cls))
        anns: dict = var.get("__annotations__", False) or dict()

        def init(self, *args, **kwargs):
            arg = {}
            if len(args) > 0:
                for i in args:
                    arg[list(anns.keys())[list(args).index(i)]] = i

            if len(kwargs) > 0:
                for i in kwargs:
                    try:
                        arg[i] = anns[i](kwargs[i])
                    except TypeError:
                        arg[i] = kwargs[i]
            new_arg = arg.copy()

            if len(anns) > len(arg):
                for i in anns.keys():
                    if i not in arg.keys():
                        if i not in var.keys():
                            new_arg[i] = None
                            continue
                        if not isinstance(var[i], anns[i]):
                            new_arg[i] = anns[i](var[i])
                        else:
                            new_arg[i] = var[i]

            for i in new_arg:
                setattr(self, i, new_arg[i])

        cls.__init__ = init

        async def to_elem(self, gid: int = None, uin: int = None) -> Union[
            elems.Text, elems.Image, elems.Audio, elems.Video, elems.Quote, elems.At, elems.AtAll, elems.Emoji, None
        ]:
            if sg_type == "at":
                if str(self.qq) == "all":
                    return elems.AtAll(text="@全体成员")
                else:
                    info = await lgr.client.get_user_info(uc.to_uid(int(self.qq)))
                    return elems.At(
                        text=f"@{info.name}",
                        uid=uc.to_uid(int(self.qq)),
                        uin=int(self.qq)
                    )
            elif sg_type == "text":
                return elems.Text(text=str(self.text))
            elif sg_type == "reply":
                seq, uin, _ = get_msg_info(int(self.id))
                return elems.Quote(
                    text="",
                    seq=seq,
                    uin=uin,
                    timestamp=0
                )
            elif sg_type == "image":
                file = str(self.file)
                if file.startswith("http"):
                    c = httpx.get(file).content
                    with open(f"./temps/image_{random.randint(1000, 9999)}", "wb") as f:
                        f.write(c)
                    c = open(f"./temps/image_{random.randint(1000, 9999)}", "rb")
                elif file.startswith("file://"):
                    c = open(file.replace("file://", "", 1), "rb")
                elif file.startswith("base64://"):
                    file = file.replace("base64://", "", 1)
                    c = base64.b64decode(file)
                    with open(f"./temps/image_{random.randint(1000, 9999)}", "wb") as f:
                        f.write(c)
                    c = open(f"./temps/image_{random.randint(1000, 9999)}", "rb")
                else:
                    c = None

                if gid is not None:
                    return await lgr.client.upload_grp_image(c, gid)
                elif uin is not None:
                    return await lgr.client.upload_friend_image(c, uc.to_uid(uin))
            elif sg_type == "record":
                file = str(self.file)
                if file.startswith("http"):
                    c = httpx.get(file).content
                    with open(f"./temps/record_{random.randint(1000, 9999)}", "wb") as f:
                        f.write(c)
                    c = open(f"./temps/record_{random.randint(1000, 9999)}", "rb")
                elif file.startswith("file://"):
                    c = open(file.replace("file://", "", 1), "rb")
                elif file.startswith("base64://"):
                    file = file.replace("base64://", "", 1)
                    c = base64.b64decode(file)
                    with open(f"./temps/image_{random.randint(1000, 9999)}", "wb") as f:
                        f.write(c)
                    c = open(f"./temps/image_{random.randint(1000, 9999)}", "rb")
                else:
                    c = None

                if gid is not None:
                    return await lgr.client.upload_grp_audio(c, gid)
                elif uin is not None:
                    return await lgr.client.upload_friend_audio(c, uc.to_uid(uin))
            else:
                return None

        cls.to_elem = to_elem

        def to_json(self) -> dict:
            base = {"type": sg_type, "data": {}}
            for i in anns:
                if getattr(self, i) is None:
                    continue
                if not isinstance(getattr(self, i), anns[i]):
                    base["data"][i] = anns[i](getattr(self, i))
                else:
                    base["data"][i] = getattr(self, i)
                # try:
                #     base["data"][i] = anns[i](getattr(self, i))
                # except TypeError:
                #     base["data"][i] = getattr(self, i)
            return base

        cls.to_json = to_json

        def to_str(self) -> str:
            text = summary_tmp
            if text is None:
                text = "[]"
            if "<" not in text and ">" not in text:
                return text

            for i in anns:
                if f"<{i}>" in summary_tmp:
                    try:
                        v = self.__getattribute__(i)
                    except AttributeError:
                        v = None
                    text = text.replace(f"<{i}>", str(v))

            return text

        cls.__str__ = to_str if cls().__str__() == "__not_set__" else cls.__str__

        def eq(self, other) -> bool:
            if type(self) is type(other) and self.to_json() == other.to_json():
                return True
            else:
                return False

        cls.__eq__ = eq

        def ne(self, other) -> bool:
            if type(self) is type(other) and self.to_json() == other.to_json():
                return False
            else:
                return True

        cls.__ne__ = ne

        message_types[sg_type] = {
            "type": cls,
            "args": list(anns.keys())
        }

        return cls

    return inner_builder


class Base:
    def __init__(self, *args, **kwargs): ...

    async def to_elem(self) -> dict: ...

    def to_json(self) -> dict: ...

    def __str__(self) -> str: return "__not_set__"

    def __eq__(self, other) -> bool: ...

    def __ne__(self, other) -> bool: ...


def to_ob_msg(chain: list):
    ob_sg = []
    for i in chain:
        if isinstance(i, elems.Quote):
            ob_sg.append(
                {
                    "type": "reply",
                    "data": {
                        "id": get_msg_id(i.seq, i.uin, 0)
                    }
                }
            )
        elif isinstance(i, elems.AtAll):
            ob_sg.append(
                {
                    "type": "at",
                    "data": {
                        "qq": "all"
                    }
                }
            )
        elif isinstance(i, elems.At):
            ob_sg.append(
                {
                    "type": "at",
                    "data": {
                        "qq": i.uin
                    }
                }
            )
        elif isinstance(i, elems.Image):
            ob_sg.append(
                {
                    "type": "image",
                    "data": {
                        "file": i.url,
                        "url": i.url
                    }
                }
            )
        elif isinstance(i, elems.Video):
            pass
        elif isinstance(i, elems.Audio):
            pass
        elif isinstance(i, elems.MarketFace):
            ob_sg.append(
                {
                    "type": "mface",
                    "data": {
                        "face_id": i.face_id,
                        "tab_id": i.tab_id,
                        "key": None
                    }
                }
            )
        elif isinstance(i, elems.Emoji):
            ob_sg.append(
                {
                    "type": "face",
                    "data": {
                        "id": i.id
                    }
                }
            )
        elif isinstance(i, elems.Json):
            ob_sg.append(
                {
                    "type": "json",
                    "data": {
                        "data": i.to_dict()
                    }
                }
            )
        elif isinstance(i, elems.Text):
            ob_sg.append(
                {
                    "type": "text",
                    "data": {
                        "text": i.text
                    }
                }
            )
        else:
            pass
    return ob_sg


def get_msg_id(seq: int, uin: int, gid: int) -> int:
    uin_bits = 32
    gid_bits = 32
    unique_id = 0
    unique_id |= int(seq) << (uin_bits + gid_bits)
    unique_id |= int(uin) << gid_bits
    unique_id |= int(gid)
    return unique_id


def get_msg_info(unique_id: int) -> tuple[int, int, int]:
    seq_bits = 16
    uin_bits = 32
    gid_bits = 32
    unique_id = int(unique_id)
    gid = unique_id & ((1 << gid_bits) - 1)
    uin = (unique_id >> gid_bits) & ((1 << uin_bits) - 1)
    seq = (unique_id >> (uin_bits + gid_bits)) & ((1 << seq_bits) - 1)
    return seq, uin, gid


async def friend_message(client: LgrCli, event: FriendMessage):
    uc.push(event.from_uid, event.from_uin)
    uc.push(event.to_uid, event.to_uin)
    o_uin = event.from_uin if event.from_uin != config.uin else event.to_uin
    sender = await client.get_user_info(uid=uc.to_uid(o_uin))

    if int(sender.sex) == 1:
        sex = "male"
    elif int(sender.sex) == 2:
        sex = "female"
    else:
        sex = "unknown"

    event_json = {
        "time": event.timestamp,
        "self_id": config.uin,
        "post_type": "message",
        "message_type": "private",
        "sub_type": "friend",
        "message_id": get_msg_id(event.seq, o_uin, 0),
        "user_id": o_uin,
        "message": to_ob_msg(event.msg_chain),
        "sender": {
            "user_id": o_uin,
            "nickname": sender.name,
            "sex": sex,
            "age": sender.age
        }
    }
    event_queue.put(event_json)


async def group_message(client: LgrCli, event: GroupMessage):
    uc.push(event.uid, event.uin)
    sender = await client.get_user_info(uid=uc.to_uid(event.uin))

    if int(sender.sex) == 1:
        sex = "male"
    elif int(sender.sex) == 2:
        sex = "female"
    else:
        sex = "unknown"

    event_json = {
        "time": event.time,
        "self_id": config.uin,
        "post_type": "message",
        "message_type": "group",
        "sub_type": "normal",
        "message_id": get_msg_id(event.seq, event.uin, event.grp_id),
        "user_id": event.uin,
        "group_id": event.grp_id,
        "message": to_ob_msg(event.msg_chain),
        "sender": {
            "user_id": event.uin,
            "nickname": sender.name,
            "card": event.nickname,
            "sex": sex,
            "age": sender.age,
            "area": f"{sender.city or ''}{sender.province or ''}{sender.country or ''}",
            "level": None,
            "role": None,
            "title": None
        },
        "anonymous": None,
        "raw_message": "",
        "font": None
    }
    event_queue.put(event_json)


lgr.subscribe(FriendMessage, friend_message)
lgr.subscribe(GroupMessage, group_message)
