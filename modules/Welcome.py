from lib import Manager, Listener, Segements
import random
import json

with open("quick.json", "r", encoding="utf-8") as f:
    quicks = json.load(f)


class ModuleClass:
    def __init__(self, actions: Listener.Actions, event: Manager.Event):
        self.actions = actions
        self.event = event

    async def handle(self):
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
            self.actions.send(group_id=self.event.group_id, message=Manager.Message(
                [Segements.Text(text)]
            ))
