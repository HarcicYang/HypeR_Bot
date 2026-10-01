from hyperot.v2 import MemberRole, Quote
from hyperot.v2.events import MemberMuteChangedEvent, MessageReceivedEvent
from typing_extensions import override

from ModuleClass import Module, ModuleInfo, ModuleRegister, is_owner


@ModuleRegister.register(MessageReceivedEvent, MemberMuteChangedEvent)
class GroupUtils(Module[MessageReceivedEvent | MemberMuteChangedEvent]):
    @override
    @staticmethod
    def info() -> ModuleInfo:
        return ModuleInfo(
            is_hidden=False,
            module_name="GroupUtils",
            desc="聊群活动实用工具",
            helps=(
                "使用:\n"
                " - 需要引用消息：\n"
                " - - .ess - 设置精华消息\n"
                " - - .resend - 发送选中消息\n"
                " - - .recall / .del - 撤回选中消息"
            ),
        )

    @override
    async def handle(self):
        if (
            isinstance(self.event, MessageReceivedEvent)
            and (
                is_owner(self.event)
                or (self.event.sender is not None and self.event.sender.role in (MemberRole.ADMIN, MemberRole.OWNER))
            )
            and len(self.event.message) >= 1
            and isinstance(self.event.message[0], Quote)
        ):
            msg_id = self.event.message[0].message_id
            if ".ess" in str(self.event.message):
                await self.api.message(str(msg_id)).set_essence()
            elif ".resend" in str(self.event.message):
                msg = await self.api.message(str(msg_id)).fetch()
                await self.api.scene(self.event.scene_type, self.event.scene_id).send(msg)
            elif ".recall" in str(self.event.message) or ".del" in str(self.event.message):
                await self.api.message(str(msg_id)).recall()
        # elif isinstance(self.event, MemberMuteChangedEvent):
        #     if int(self.event.operator_id) in [2705264881] and int(self.event.user_id) in [2488529467]:
        #         await self.actions.set_group_ban(self.event.group_id, self.event.user_id, 0)
        # await self.actions.set_group_ban(self.event.group_id, 2101596336, self.event.duration)
