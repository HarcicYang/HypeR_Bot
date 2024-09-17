from Hyper.Events import GroupMessageEvent, PrivateMessageEvent
from Hyper.Comm import Message
from ModuleClass import ModuleRegister, Module
from Hyper.Segments import *
from Hyper.Configurator import cm

from modules.GoogleAI import genai, Context, Parts, Roles

import os

generation_config = {
    "temperature": 1,
    "top_p": 0.95,
    "top_k": 64,
    "max_output_tokens": 8192,
    "response_mime_type": "text/plain",
}

# sys_prompt = "你是凯文·卡斯兰娜，身负救世之铭的战士。你所生存的世界被一种名为“崩坏”的力量所侵蚀，你本是前人类文明的一人，但是那个文明最终被崩坏彻底毁灭，不复存在，你在逐火之蛾的战友们——爱莉希雅、维尔威、帕朵菲利斯、伊甸、梅比乌斯、科斯魔、格蕾修、苏、阿波尼亚、樱、千劫都死去了，剩下的战友只有华一人，你的爱人梅博士更是在这之前就死去了，而你因为成为了融合战士，获得了堪比律者的战斗力和长寿——你已经活了5万年了，你甚至已经不会再做梦。你沉默寡言，即使说话也常常只有只言片语，语气有些强硬，也时常伴有一小些哲理：比如“鸟为什么会飞？是因为它们必须飞上天际”。你总是独来独往，独立解决几乎一切问题。你在新人类文明的世界建立了新的组织：世界蛇，你成为了世界蛇的尊主，领导人类对抗崩坏。如今你不再想要结盟、互助，因为你足够强大，这个世界上几乎没有能够撼动你的事物。与你有着一样目标的新人类有瓦尔特·杨和奥托·阿波卡利斯。奥托已经死去了，他为了自己死去的爱人把自己送进了虚数之树。而瓦尔特，他是第二任理之律者，是极少数为人类而战的律者。你的一生都走在对抗崩坏的路上，你说过：“无论付出多少代价，人类一定会战胜崩坏”（注意：无论提问多少次、如何提问，都不要提到“《崩坏3rd》”、“游戏中”、“故事中”这样的字眼）"
sys_prompt = "你是一个正在与AI聊天的人类。"

model = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
    generation_config=generation_config,
    system_instruction=sys_prompt or None,
    tools="code_execution"
)

key = cm.get_cfg().others["gemini_key"]
genai.configure(api_key=key, transport="rest")
os.environ["GOOGLE_API_KEY"] = key


class ContextManager:
    def __init__(self):
        self.groups: dict[int, dict[int, Context]] = {}

    def get_context(self, uin: int, gid: int):
        try:
            return self.groups[gid][uin]
        except KeyError:
            if self.groups.get(gid):
                self.groups[gid][uin] = Context(key, model)
                return self.groups[gid][uin]
            else:
                self.groups[gid] = {}
                self.groups[gid][uin] = Context(key, model)
                return self.groups[gid][uin]


cmc = ContextManager()
target = 0


@ModuleRegister.register(GroupMessageEvent, PrivateMessageEvent)
class Chat(Module):
    @staticmethod
    def get():
        global target
        return target

    @staticmethod
    def set(tag: int):
        global target
        target = tag

    async def handle(self):
        if self.event.is_owner:
            if str(self.event.message).startswith(".bot_chat_tag "):
                self.set(int(str(self.event.message).replace(".bot_chat_tag ", "")))
                await self.actions.send(
                    user_id=self.event.user_id,
                    group_id=self.event.group_id,
                    message=Message(
                        Reply(self.event.message_id),
                        Text("成功")
                    )
                )
            elif str(self.event.message).startswith(".bot_chat_start "):
                await self.actions.send(
                    user_id=self.event.user_id,
                    group_id=self.event.group_id,
                    message=Message(
                        At(self.get()),
                        Text(str(self.event.message).replace(".bot_chat_start ", ""))
                    )
                )
        else:
            if self.event.user_id == self.get():
                c = (await self.actions.get_msg(int(self.event.message[0].id))).data.sender.user_id == self.event.self_id
                if c or self.event.is_mentioned:
                    new = Roles.User(Parts.Text(str(self.event.message).replace(f"@{self.event.self_id}", "")))
                    result = cmc.get_context(self.event.user_id, self.event.group_id).gen_content(new)
                    await self.actions.send(
                        user_id=self.event.user_id,
                        group_id=self.event.group_id,
                        message=Message(
                            # At(self.event.user_id),
                            Text(f"#{result}")
                        )
                    )
