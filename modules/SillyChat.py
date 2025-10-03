import hyperot
from hyperot import events, segments, common
import ModuleClass
from hyperot.events import GroupMessageEvent, PrivateMessageEvent

from .GuesserTools.shitchatter import silly_chatter


@ModuleClass.ModuleRegister.register(GroupMessageEvent, PrivateMessageEvent)
class Module(ModuleClass.Module):
    @staticmethod
    def filter(event: events.Event, allowed: list) -> bool:
        if isinstance(event, PrivateMessageEvent) and len(event.message) != 0 and str(event.message).startswith("sb"):
            return True
        elif (
                isinstance(event, GroupMessageEvent)
                and isinstance(event.message[0], segments.At)
                and str(event.message[0].qq) == str(event.self_id)
        ):
            return True

        return False

    async def handle(self):
        pure_msg = common.Message(segments.Text(""))
        for i in self.event.message:
            if not isinstance(i, segments.Text):
                continue
            pure_msg.add(i)
        text = str(pure_msg)
        reply = silly_chatter(text)
        await self.actions.send(
            group_id=self.event.group_id,
            user_id=self.event.user_id,
            message=reply
        )

