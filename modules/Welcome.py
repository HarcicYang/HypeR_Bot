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
                text = str(quicks["group_increase"][random.randint(0, len(quicks["group_increase"]) - 1)]).replace(
                    "<user>", str(self.event.user_id))
            elif self.event.notice_type == "group_decrease":
                try:
                    text = str(quicks["group_decrease"][self.event.sub_type][
                                   random.randint(0, len(quicks["group_decrease"][self.event.sub_type]) - 1)
                               ]).replace("<user>", str(self.event.user_id))
                except KeyError:
                    return None
            else:
                return None
            await self.actions.send(group_id=self.event.group_id, message=Manager.Message(
                [Segments.Text(text)]
            ))

        elif self.event.post_type == "request":
            if self.event.request_type == "group":

                if self.event.sub_type == "add":
                    if str(self.event.group_id) == "615504117" or str(self.event.group_id) == "615461114":
                        if "前一节的补充" in self.event.comment:
                            pass
                        else:
                            await self.actions.set_group_add_request(flag=self.event.flag, sub_type=self.event.sub_type,
                                                                     approve=False)
                            return

                    await self.actions.set_group_add_request(flag=self.event.flag, sub_type=self.event.sub_type,
                                                             approve=True)
                elif self.event.sub_type == "invite":
                    message = Manager.Message(
                        [
                            Segments.Text(f"HypeR Bot 通过用户{self.event.user_id}的邀请加入群组")
                        ]
                    )
                    await self.actions.send(group_id=self.event.group_id, message=message)
