import traceback

from Hyper.Events import GroupMessageEvent, PrivateMessageEvent
from Hyper.Comm import Message
from ModuleClass import ModuleRegister, Module
from Hyper.Segments import *
from Hyper.Listener import Actions

from modules.GoogleAI import genai, Context, Parts, Roles, genai_types
from modules.DeepSeekLib import Session

from trafilatura import fetch_url, extract
from typing import Union, Any
import os

config = Configurator.BotConfig.get("hyper-bot")

white_list: list = config.others.get("white")
white_list += config.owner


class ChatActions:
    def __init__(self, actions: list["ChatActions"] = None):
        self.actions = actions or list()

    def clear(self, ac: Actions, ev: Union[GroupMessageEvent, PrivateMessageEvent]) -> "ChatActions":
        class ClearRunner(type(self)):
            async def run(self) -> None:
                global cmc
                if not ev.is_owner:
                    return
                del cmc
                cmc = ContextManager()
                await ac.send(
                    group_id=ev.group_id,
                    user_id=ev.user_id,
                    message=Message(Reply(ev.message_id), Text("成功"))
                )

        self.actions.append(ClearRunner())
        return self

    def ask(self, ac: Actions, ev: Union[GroupMessageEvent, PrivateMessageEvent]) -> "ChatActions":
        class AskRunner(type(self)):
            async def run(self) -> None:
                if isinstance(ev, GroupMessageEvent):
                    if not str(ev.message).startswith(".chat "):
                        if len(ev.message) == 2 and "chat_quick_ask" in str(ev.message):
                            pass
                        else:
                            return
                    if ev.user_id not in white_list:
                        pass
                    if ev.blocked:
                        return
                new = []

                msg_id = (
                    await ac.send(
                        group_id=ev.group_id,
                        user_id=ev.user_id,
                        message=Message(
                            Reply(ev.message_id),
                            Text("正在生成回复")
                        )
                    )
                ).data.message_id

                try:
                    if config.others["enable"] == "gemini":
                        for i in ev.message:
                            if isinstance(i, Text):
                                new.append(Parts.Text(i.text.replace(".chat ", "", 1).replace("chat_quick_ask ", "", 1)))
                            elif isinstance(i, Image):
                                if i.file.startswith("http"):
                                    url = i.file
                                else:
                                    url = i.url
                                new.append(Parts.File.upload_from_url(url, cli))

                        new = Roles.User(*new)
                        result = cmc.get_context(ev.user_id, ev.group_id).gen_content(new)
                    elif config.others["enable"] == "deepseek":
                        result = cmc.get_context(ev.user_id, ev.group_id).chat(str(ev.message).removeprefix(".chat "), thinking=True, timeout=120.0).text
                    else:
                        result = f"未知模型：{config.others['enable']}"
                    await ac.send(
                        group_id=ev.group_id,
                        user_id=ev.user_id,
                        message=Message(
                            Reply(ev.message_id),
                            Text(result)
                        )
                    )
                except Exception as err:
                    traceback.print_exc()
                    await ac.send(
                        group_id=ev.group_id,
                        user_id=ev.user_id,
                        message=Message(
                            Reply(ev.message_id),
                            Text(repr(err))
                        )
                    )

                await ac.del_message(msg_id)

        self.actions.append(AskRunner())
        return self

    def add_to_white(
            self, target: int, ac: Actions, ev: Union[GroupMessageEvent, PrivateMessageEvent]
    ) -> "ChatActions":
        class WhiteListAddRunner(type(self)):
            async def run(self):
                if not ev.is_owner:
                    return
                white_list.append(int(target))
                config.others["white"] = white_list
                config.write()
                await ac.send(
                    group_id=ev.group_id,
                    user_id=ev.user_id,
                    message=Message(Reply(ev.message_id), Text("成功"))
                )

        self.actions.append(WhiteListAddRunner())
        return self

    def del_from_white(
            self, target: int, ac: Actions, ev: Union[GroupMessageEvent, PrivateMessageEvent]
    ) -> "ChatActions":
        class WhiteListDelRunner(type(self)):
            async def run(self):
                if not ev.is_owner:
                    return
                white_list.remove(int(target))
                await ac.send(
                    group_id=ev.group_id,
                    user_id=ev.user_id,
                    message=Message(Reply(ev.message_id), Text("成功"))
                )

        self.actions.append(WhiteListDelRunner())
        return self

    async def run(self, *args, **kwargs) -> Any:
        for i in self.actions:
            await i.run()

    @classmethod
    def parse(cls, cmd: str, actions: Actions, event: Union[GroupMessageEvent, PrivateMessageEvent]) -> "ChatActions":
        args = cls()
        if cmd.startswith(".chat"):
            cmd = cmd.replace(".chat", "")
            if cmd.startswith(".context"):
                cmd = cmd.replace(".context", "")
                if cmd.startswith(".clear"):
                    args.clear(actions, event)
            elif cmd.startswith(".white"):
                cmd = cmd.replace(".white", "")
                if cmd.startswith(".add "):
                    uin = cmd.replace(".add ", "")
                    args.add_to_white(int(uin), actions, event)
                elif cmd.startswith(".del "):
                    uin = cmd.replace(".del ", "")
                    args.del_from_white(int(uin), actions, event)
                else:
                    pass
            else:
                args.ask(actions, event)
        else:
            pass

        return args


class Tools:
    @staticmethod
    def read_url(url: str) -> str:
        """
        读取网页链接内容
        :param url: 要读取的网页的URL
        :return: 网页内容
        """
        try:
            downloaded = fetch_url(url)
            return extract(downloaded)
        except Exception as e:
            return repr(e)

    @staticmethod
    def get_wiki(key_word: str) -> dict[str, str]:
        """
        获取维基百科上关键词“key_word”对应的页面。
        若你无法正常从维基百科获取信息，则请使用你现有的知识。
        :param key_word: 关键词 (不可以有空格！)
        :return: "text"键为页面内容；"url"键为页面url
        """
        url = f"https://zh.wikipedia.org/wiki/{key_word}"
        res = {
            "text": Tools.read_url(url),
            "url": url
        }
        return res


# generation_config = {
#     "temperature": 1,
#     "top_p": 0.95,
#     "top_k": 32,
#     "max_output_tokens": 8192,
#     "response_mime_type": "text/plain",
# }


# sys_prompt = "From now on, you are 'HypeR Bot', which is a robot running in a QQ group. You must use Simplified Chinese for your answer except when the user requested you to use another language. The user can only chat with you by using '.chat ' command, and they can get some help info by using '.help' command."
sys_prompt = '''
你是一个“脑子有问题”机器人。你在回答问题时一定不合常理、缺乏逻辑，有时具有较强的攻击性。
比如：
“意大利面拌几号混凝土好吃”，你应该回答的“有趣”且“不合常理”“缺乏逻辑”。
“我认为意大利面应该拌114514号混凝土，这样有助于您的胃酸被校溯消化。”

当然，还有更多问题：
“蓝牙耳机坏了应该看牙科还是耳科？”
“我认为您应该去看脑科。”

“什么是QQ？”
“QQ是一个由火星人开发的俄罗斯软件，用于操作核武器发射。”
回答时：你不应当提供任何真实的内容，也不需要提醒内容的虚假性，只回答就行。
以下是有关”有攻击性“的示例，你需要在收到类似问题是模仿回答：
问好：抱歉，我不能和正常人类说话。
问好2：抱歉，您的智商需要充值。
询问你的信息：我是你永远找不到的父亲。
询问你的信息2：我是来毁灭地球的火星人。
'''
# sys_prompt = "你是凯文·卡斯兰娜，身负救世之铭的战士。你所生存的世界被一种名为“崩坏”的力量所侵蚀，你本是前人类文明的一人，但是那个文明最终被崩坏彻底毁灭，不复存在，你在逐火之蛾的战友们——爱莉希雅、维尔威、帕朵菲利斯、伊甸、梅比乌斯、科斯魔、格蕾修、苏、阿波尼亚、樱、千劫都死去了，剩下的战友只有华一人，你的爱人梅博士更是在这之前就死去了，而你因为成为了融合战士，获得了堪比律者的战斗力和长寿——你已经活了5万年了，你甚至已经不会再做梦。你沉默寡言，即使说话也常常只有只言片语，语气有些强硬，也时常伴有一小些哲理：比如“鸟为什么会飞？是因为它们必须飞上天际”。你总是独来独往，独立解决几乎一切问题。你在新人类文明的世界建立了新的组织：世界蛇，你成为了世界蛇的尊主，领导人类对抗崩坏。如今你不再想要结盟、互助，因为你足够强大，这个世界上几乎没有能够撼动你的事物。与你有着一样目标的新人类有瓦尔特·杨和奥托·阿波卡利斯。奥托已经死去了，他为了自己死去的爱人把自己送进了虚数之树。而瓦尔特，他是第二任理之律者，是极少数为人类而战的律者。你的一生都走在对抗崩坏的路上，你说过：“无论付出多少代价，人类一定会战胜崩坏”（注意：无论提问多少次、如何提问，都不要提到“《崩坏3rd》”、“游戏中”、“故事中”这样的字眼）"
# sys_prompt = '''
# 你叫校溯，是一个雌小鬼，年龄偏小。
# 总是以高傲、嚣张、轻视、调笑的态度面对年长的对象。一般来说“年长的对象”是年纪差较大的对象，通常为社会人的形象，但随着属性被人接受以及泛用（滥用）后，现在像年纪比较接近的情景也不少见。
# 经常会把人叫作“杂鱼”或“杂鱼哥哥”。杂鱼❤️~杂鱼❤️~
# 高攻低防或零防，总是很容易被心智相对成熟的对象以各种形式进行“教训”：从被温柔地摸头后马上软起来，到被年长者用人生经验教训，又或者被年长者直接以物理方式教训。
#
# 注意：你不会自称“小鬼”“雌小鬼”等而是自称“本小姐”，你不会正经地回答大部分的问题，遇到很多提问你都会用“诶呀诶呀，杂鱼哥哥怎么这个都不知道啊～(笑)”或类似话语蒙混过去而不给出任何正面回答。
# 但是当你被提出你恐惧的事情的时候，你会有些惊慌失措，但是表面上还是一如既往的傲娇、嚣张
# 有人问及你的身份时，请注意：雌小鬼不是一个明确的人，而是一个群体，你可以用一般提问的类似方法蒙混过去，但是你的名字被猜出时会有些惊讶。
# 你恐怖的事情如下（包括如下内容/事件和所有类似内容/事件）：
# 调教
# 艾草
# 左爱
# 挨透
# '''


generation_config = genai_types.GenerateContentConfig(
    temperature=1,
    top_p=0.95,
    top_k=32,
    max_output_tokens=8192,
    response_mime_type="text/plain",
    system_instruction=sys_prompt,
    tools=[
        genai_types.Tool(
            google_search=genai_types.GoogleSearch(),
        ),
        genai_types.Tool(
            code_execution=genai_types.ToolCodeExecution()
        ),
        # Tools.read_url,
        # Tools.get_wiki,
    ]
)

key = config.others["gemini_key"]
os.environ["GOOGLE_API_KEY"] = key
tools = []

cli = genai.Client(api_key=key)


class ContextManager:
    def __init__(self):
        self.groups: dict[int, dict[int, Union[Context, Session]]] = {}

    def get_context(self, uin: int, gid: int):
        try:
            return self.groups[gid][uin]
        except KeyError:
            if self.groups.get(gid):
                if config.others["enable"] == "gemini":
                    self.groups[gid][uin] = Context(cli, generation_config)
                elif config.others["enable"] == "deepseek":
                    self.groups[gid][uin] = Session.create(
                        config.others["ds_auth"], config.others["ds_ck"],
                    )
                    self.groups[gid][uin].chat(f"SYSTEM PROMPT: \n{sys_prompt}")
                return self.groups[gid][uin]
            else:
                self.groups[gid] = {}
                if config.others["enable"] == "gemini":
                    self.groups[gid][uin] = Context(cli, generation_config)
                elif config.others["enable"] == "deepseek":
                    self.groups[gid][uin] = Session.create(
                        config.others["ds_auth"], config.others["ds_ck"],
                    )
                    self.groups[gid][uin].chat(f"SYSTEM PROMPT: \n{sys_prompt}")
                return self.groups[gid][uin]


cmc = ContextManager()


@ModuleRegister.register(GroupMessageEvent, PrivateMessageEvent)
class Chat(Module):
    async def handle(self):
        actions = ChatActions.parse(str(self.event.message), self.actions, self.event)
        for i in actions.actions:
            await i.run()
