from Hyper.Events import GroupMessageEvent, PrivateMessageEvent
from Hyper.Manager import Message
from ModuleClass import ModuleRegister, Module
from Hyper.Segments import *
from Hyper.Configurator import cm
from Hyper.Listener import Actions

from modules.GoogleAI import genai, Context, Parts, Roles

from typing import Union, Any
from search_engines import Bing
import html2text
import random
import subprocess
import traceback
import os
import httpx

white_list: list = cm.get_cfg().others.get("white")
white_list += cm.get_cfg().owner


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
                        return
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
                            new.append(Parts.File.upload_from_url(url))

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

    @staticmethod
    def search_web(query: str) -> list:
        """
        在网络上搜索一个关键词（句）
        :param query: 要搜索的关键词（句）
        :return: 一个list，包含了搜索到的结果。
        """

        def read_url(url: str) -> str:
            try:
                headers = {
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36"
                }
                h = html2text.HTML2Text()
                response = h.handle(httpx.get(url, headers=headers, verify=False).text)
            except Exception as e:
                response = str(e)
            return response

        engine = Bing()
        results = engine.search(query, pages=1)
        links = results.links()
        titles = results.titles()
        dic = []
        for i in range(2):
            try:
                dic.append({"title": titles[i], "link": links[i], "content": read_url(links[i])})
            except IndexError:
                break

        return dic


generation_config = {
    "temperature": 1,
    "top_p": 0.95,
    "top_k": 64,
    "max_output_tokens": 8192,
    "response_mime_type": "text/plain",
}

sys_prompt = "你是HypeR Bot"

model = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
    generation_config=generation_config,
    system_instruction=sys_prompt or None,
    tools="code_execution"
)

key = cm.get_cfg().others["gemini_key"]
genai.configure(api_key=key, transport="rest")
os.environ["GOOGLE_API_KEY"] = key
tools = [Tools.read_url]


class ContextManager:
    def __init__(self):
        self.groups: dict[int, dict[int, Context]] = {}

    def get_context(self, uin: int, gid: int):
        try:
            return self.groups[gid][uin]
        except KeyError:
            if self.groups.get(gid):
                self.groups[gid][uin] = Context(key, model, tools=tools)
                return self.groups[gid][uin]
            else:
                self.groups[gid] = {}
                self.groups[gid][uin] = Context(key, model, tools=tools)
                return self.groups[gid][uin]


cmc = ContextManager()


@ModuleRegister.register(GroupMessageEvent, PrivateMessageEvent)
class Chat(Module):
    async def handle(self):
        actions = ChatActions.parse(str(self.event.message), self.actions, self.event)
        for i in actions.actions:
            await i.run()
