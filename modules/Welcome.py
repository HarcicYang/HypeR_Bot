from Hyper import Segments, Comm
import ModuleClass
from Hyper.Events import *
import random
import json

with open("./assets/quick.json", "r", encoding="utf-8") as f:
    quicks = json.load(f)

cache = {}


@ModuleClass.ModuleRegister.register(GroupAddInviteEvent, GroupMemberDecreaseEvent, GroupMemberIncreaseEvent, GroupMessageEvent)
class Module(ModuleClass.Module):
    async def handle(self):
        if self.event.blocked or self.event.is_silent:
            return
        if isinstance(self.event, NoticeEvent):
            if isinstance(self.event, GroupMemberIncreaseEvent):
                text = str(random.choice(quicks["group_increase"])).split("<user>")
                await self.actions.send(group_id=self.event.group_id, message=Comm.Message(
                    [
                        Segments.Text(text[0]),
                        Segments.At(self.event.user_id),
                        Segments.Text(text[1])
                    ]
                ))
            elif isinstance(self.event, GroupMemberDecreaseEvent):
                try:
                    text = str(random.choice(quicks["group_decrease"][self.event.sub_type])).replace("<user>", str(self.event.user_id))
                    await self.actions.send(group_id=self.event.group_id, message=Comm.Message(
                        [
                            Segments.Text(text)
                        ]
                    ))

                except KeyError:
                    return None
            else:
                return None

        elif isinstance(self.event, RequestEvent):
            if isinstance(self.event, GroupAddInviteEvent):
                if self.event.sub_type == "add":
                    # await self.actions.set_group_add_request(flag=self.event.flag, sub_type=self.event.sub_type,
                    #                                          approve=True)
                    # await self.actions.send(group_id=self.event.group_id, message=Comm.Message(
                    #     [
                    #         Segments.Text("同意用户"), Segments.At(self.event.user_id), Segments.Text("的加群请求。"),
                    #         Segments.Text("\n"),
                    #         Segments.Text(str(self.event.comment))
                    #     ]
                    # ))
                    uinfo = await self.actions.get_stranger_info(self.event.user_id)
                    msg = await self.actions.send(group_id=self.event.group_id, message=Comm.Message(
                        [
                            Segments.Text(f"有新的入群请求，来自用户 {uinfo.data.nickname}（QQ {self.event.user_id}），请尽快处理")
                        ]
                    ))
                    cache[str(msg.data.message_id)] = [self.event.comment, self.event.flag]
                elif self.event.sub_type == "invite":
                    message = Comm.Message(
                        [
                            Segments.Text(f"HypeR Bot 通过用户 QQ {self.event.user_id}的邀请加入群组")
                        ]
                    )
                    await self.actions.send(group_id=self.event.group_id, message=message)
        elif isinstance(self.event, GroupMessageEvent):
            _id = None
            for i in self.event.message:
                if isinstance(i, Segments.Reply):
                    _id = i.id
                    break
            if _id:
                if ".comment" in str(self.event.message):
                    await self.actions.send(
                        group_id=self.event.group_id, user_id=self.event.user_id,
                        message=Comm.Message(
                            Segments.Reply(self.event.message_id),
                            Segments.Text(cache[str(_id)][0])
                        )
                    )
                elif ".approve" in str(self.event.message):
                    await self.actions.set_group_add_request(
                        flag=cache[str(_id)][1], sub_type=self.event.sub_type, approve=True
                    )
