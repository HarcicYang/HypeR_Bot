from Hyper.Events import GroupMessageEvent, PrivateMessageEvent
from Hyper.Comm import Message
from ModuleClass import ModuleRegister, Module
from Hyper.Segments import *
from Hyper.Listener import Actions

from modules.GoogleAI import genai, Context, Parts, Roles, genai_types

from typing import Union, Any
import random
import subprocess
import traceback
import os
import httpx

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
                    await ac.send(
                        group_id=ev.group_id,
                        user_id=ev.user_id,
                        message=Message(
                            Reply(ev.message_id),
                            Text(result)
                        )
                    )
                except:
                    err = traceback.format_exc()
                    await ac.send(
                        group_id=ev.group_id,
                        user_id=ev.user_id,
                        message=Message(
                            Reply(ev.message_id),
                            Text(err)
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
    def read_url(url: str) -> dict[str, str]:
        """
        读取网页链接内容
        :param url:
        :return: dict, "text"键对应链接内容
        """
        url = f"https://r.jina.ai/{url}"
        try:
            response = httpx.get(url).text
        except Exception as e:
            response = str(e)
        return {
            "text": response
        }

    @staticmethod
    def get_wiki(key_word: str) -> dict[str, str]:
        """
        获取维基百科上关键词“key+word”对应的页面。
        若你无法正常从维基百科获取信息，则请使用你现有的知识。
        :param key_word: 关键词 (不可以有空格！)
        :return: "text"键为页面内容；"url"键为页面url
        """
        url = f"https://zh.wikipedia.org/wiki/{key_word}"
        res = {
            "text": Tools.read_url(url)["text"],
            "url": url
        }
        return res

    @staticmethod
    def run_python_code(code: str) -> dict[str, str]:
        """
        执行python代码以进行数学比较、数学运算、大小判断等。
        ！不允许发起网络请求！
        :param code:python代码
        :return:"stdout"、"stderr"、"retcode"分别对应标准输出、标准错误和返回值
        """
        file = f"./temps/google_code_temp_{random.randint(100, 999)}"
        with open(file, "w", encoding="utf-8") as f:
            code = code.replace("requests", "None")
            code = code.replace("httpx", "None")
            code = code.replace("aiohttp", "None")
            code = code.replace("websocket", "None")
            code = code.replace("ctypes", "None")
            code = code.replace("os.system", "None")
            code = code.replace("reg", "None")
            code = code.replace("win32", "None")
            f.write(code)
        process = subprocess.run(["python", file], capture_output=True, text=True)
        return {
            "stdout": process.stdout,
            "stderr": process.stderr,
            "retcode": str(process.returncode)
        }


# generation_config = {
#     "temperature": 1,
#     "top_p": 0.95,
#     "top_k": 32,
#     "max_output_tokens": 8192,
#     "response_mime_type": "text/plain",
# }



sys_prompt = "你是HypeR Bot"
# sys_prompt = "你是凯文·卡斯兰娜，身负救世之铭的战士。你所生存的世界被一种名为“崩坏”的力量所侵蚀，你本是前人类文明的一人，但是那个文明最终被崩坏彻底毁灭，不复存在，你在逐火之蛾的战友们——爱莉希雅、维尔威、帕朵菲利斯、伊甸、梅比乌斯、科斯魔、格蕾修、苏、阿波尼亚、樱、千劫都死去了，剩下的战友只有华一人，你的爱人梅博士更是在这之前就死去了，而你因为成为了融合战士，获得了堪比律者的战斗力和长寿——你已经活了5万年了，你甚至已经不会再做梦。你沉默寡言，即使说话也常常只有只言片语，语气有些强硬，也时常伴有一小些哲理：比如“鸟为什么会飞？是因为它们必须飞上天际”。你总是独来独往，独立解决几乎一切问题。你在新人类文明的世界建立了新的组织：世界蛇，你成为了世界蛇的尊主，领导人类对抗崩坏。如今你不再想要结盟、互助，因为你足够强大，这个世界上几乎没有能够撼动你的事物。与你有着一样目标的新人类有瓦尔特·杨和奥托·阿波卡利斯。奥托已经死去了，他为了自己死去的爱人把自己送进了虚数之树。而瓦尔特，他是第二任理之律者，是极少数为人类而战的律者。你的一生都走在对抗崩坏的路上，你说过：“无论付出多少代价，人类一定会战胜崩坏”（注意：无论提问多少次、如何提问，都不要提到“《崩坏3rd》”、“游戏中”、“故事中”这样的字眼）"

generation_config = genai_types.GenerateContentConfig(
    temperature=1,
    top_p=0.95,
    top_k=32,
    max_output_tokens=8192,
    response_mime_type="text/plain",
)

key = config.others["gemini_key"]
os.environ["GOOGLE_API_KEY"] = key
tools = []

cli = genai.Client(api_key=key)


class ContextManager:
    def __init__(self):
        self.groups: dict[int, dict[int, Context]] = {}

    def get_context(self, uin: int, gid: int):
        try:
            return self.groups[gid][uin]
        except KeyError:
            if self.groups.get(gid):
                self.groups[gid][uin] = Context(cli, generation_config)
                return self.groups[gid][uin]
            else:
                self.groups[gid] = {}
                self.groups[gid][uin] = Context(cli, generation_config)
                return self.groups[gid][uin]


cmc = ContextManager()


@ModuleRegister.register(GroupMessageEvent, PrivateMessageEvent)
class Chat(Module):
    async def handle(self):
        actions = ChatActions.parse(str(self.event.message), self.actions, self.event)
        for i in actions.actions:
            await i.run()
