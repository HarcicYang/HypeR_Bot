from Hyper import Manager, ModuleClass, Segments
import random
import json

with open("quick.json", "r", encoding="utf-8") as f:
    quicks = json.load(f)


@ModuleClass.ModuleRegister.register(["notice", "request"])
class Module(ModuleClass.Module):
    async def handle(self):
        if self.event.blocked or self.event.servicing:
            return
        if self.event.post_type == "notice":
            if self.event.notice_type == "group_increase":
                text = str(random.choice(quicks["group_increase"])).split("<user>")
                await self.actions.send(group_id=self.event.group_id, message=Manager.Message(
                    [
                        Segments.Text(text[0]),
                        Segments.At(self.event.user_id),
                        Segments.Text(text[1])
                    ]
                ))
            elif self.event.notice_type == "group_decrease":
                try:
                    text = str(random.choice(quicks["group_decrease"][self.event.sub_type])).replace("<user>", str(self.event.user_id))
                    await self.actions.send(group_id=self.event.group_id, message=Manager.Message(
                        [
                            Segments.Text(text)
                        ]
                    ))

                except KeyError:
                    return None
            else:
                return None

        elif self.event.post_type == "request":
            if self.event.request_type == "group":
                if self.event.sub_type == "add":
                    await self.actions.set_group_add_request(flag=self.event.flag, sub_type=self.event.sub_type,
                                                             approve=True)
                    await self.actions.send(group_id=self.event.group_id, message=Manager.Message(
                        [
                            Segments.Text("同意用户"), Segments.At(self.event.user_id), Segments.Text("的加群请求。"),
                            Segments.Text("\n"),
                            Segments.Text(str(self.event.comment))
                        ]
                    ))
                elif self.event.sub_type == "invite":
                    message = Manager.Message(
                        [
                            Segments.Text(f"HypeR Bot 通过用户{self.event.user_id}的邀请加入群组")
                        ]
                    )
                    await self.actions.send(group_id=self.event.group_id, message=message)
