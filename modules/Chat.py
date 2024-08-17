from Hyper.Events import GroupMessageEvent, PrivateMessageEvent
from Hyper.Manager import Message
from ModuleClass import ModuleRegister, Module
from Hyper.Segments import *
from Hyper.Configurator import cm

from modules.GoogleAI import genai, Context, Parts, Roles

import random
import subprocess
import traceback
import os
import httpx

white_list = cm.get_cfg().others.get("white")
white_list += cm.get_cfg().owner


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


generation_config = {
    "temperature": 1,
    "top_p": 0.95,
    "top_k": 64,
    "max_output_tokens": 8192,
    "response_mime_type": "text/plain",
}

sys_prompt = "你是由Google开发的大语言模型，你叫Gemini，具体型号是Gemini-1.5-Flash"

model = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
    generation_config=generation_config,
    system_instruction=sys_prompt or None,
    tools=[Tools.read_url, Tools.get_wiki, Tools.run_python_code]
)

key = cm.get_cfg().others["gemini_key"]
genai.configure(api_key=key)
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
        if isinstance(self.event, GroupMessageEvent):
            if not str(self.event.message).startswith(".chat "):
                if len(self.event.message) == 2 and "chat_quick_ask" in str(self.event.message):
                    pass
                else:
                    return
            if self.event.user_id not in white_list:
                return
            if self.event.blocked:
                return
        new = []

        msg_id = (
            await self.actions.send(
                group_id=self.event.group_id,
                user_id=self.event.user_id,
                message=Message(
                    Reply(self.event.message_id),
                    Text("正在生成回复")
                )
            )
        ).data.message_id

        try:
            for i in self.event.message:
                if isinstance(i, Text):
                    new.append(Parts.Text(i.text.replace(".chat ", "", 1).replace("chat_quick_ask ", "", 1)))
                elif isinstance(i, Image):
                    if i.file.startswith("http"):
                        url = i.file
                    else:
                        url = i.url
                    new.append(Parts.File.upload_from_url(url))

            new = Roles.User(*new)
            result = cmc.get_context(self.event.user_id, self.event.group_id).gen_content(new)
            await self.actions.send(
                group_id=self.event.group_id,
                user_id=self.event.user_id,
                message=Message(
                    Reply(self.event.message_id),
                    Text(result[:len(result) - 1])
                )
            )
        except:
            err = traceback.format_exc()
            await self.actions.send(
                group_id=self.event.group_id,
                user_id=self.event.user_id,
                message=Message(
                    Reply(self.event.message_id),
                    Text(err)
                )
            )

        await self.actions.del_message(msg_id)
