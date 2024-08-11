from Hyper.Events import GroupMessageEvent, PrivateMessageEvent
from Hyper.Manager import Message
from Hyper.ModuleClass import ModuleInfo, ModuleRegister, Module
from Hyper.Segments import *
from Hyper.Configurator import cm

from modules.GoogleAI import genai, Context, Parts, Roles

import traceback
import os
import httpx


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


generation_config = {
    "temperature": 1,
    "top_p": 0.95,
    "top_k": 64,
    "max_output_tokens": 8192,
    "response_mime_type": "text/plain",
}

sys_prompt = "None"

model = genai.GenerativeModel(
    model_name="gemini-1.5-flash",
    generation_config=generation_config,
    system_instruction=sys_prompt,
    tools=[Tools.read_url]
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
                return
            if not self.event.is_owner:
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
                    new.append(Parts.Text(i.text.replace(".chat ", "", 1)))
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
