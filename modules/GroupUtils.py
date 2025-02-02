from Hyper.Comm import Message
from ModuleClass import Module, ModuleInfo, ModuleRegister
from Hyper.Segments import Text, Reply, At
from Hyper.Events import GroupMessageEvent


@ModuleRegister.register(GroupMessageEvent)
class GroupUtils(Module):
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
            )
        )

    async def handle(self):
        if not self.event.is_owner and self.event.sender.role not in ["admin", "owner"]:
            return

        if len(self.event.message) >= 1:
            if isinstance(self.event.message[0], Reply):
                msg_id = self.event.message[0].id
                if ".ess" in str(self.event.message):
                    await self.actions.set_essence_msg(int(msg_id))
                elif ".resend" in str(self.event.message):
                    msg = (await self.actions.get_msg(msg_id)).data.message
                    await self.actions.send(group_id=self.event.group_id, user_id=self.event.user_id, message=msg)
                elif ".recall" in str(self.event.message) or ".del" in str(self.event.message):
                    await self.actions.del_message(msg_id)
