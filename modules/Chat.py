from lib import Manager, Listener, Segments, DataBase, Configurator
import dashscope
from dashscope import Generation
from dashscope import MultiModalConversation

dataset = DataBase.Dataset()
with open("sys_prompt.txt", "r", encoding="utf-8") as f:
    sys_prompt = f.read()

config = Configurator.Config("config.json")
dashscope.api_key = config.others["Chat"]["Qwen"]["key"]


class LLM:
    def __init__(self, user_id: int, message: str, raw_message: Manager.Message):
        self.user_id = user_id
        self.message = message
        self.raw_message = raw_message
        self.sys_prompt = sys_prompt
        self.mapping = {
            "qwen": self.ask_qwen,
            "qwenvl": self.ask_qwenvl,
        }

    def handle(self) -> str:
        global mode
        if mode in self.mapping:
            result = self.mapping[mode]()
            # print(result)
            return result
        else:
            return "错误的模式"

    def ask_qwen(self) -> str:
        new = [{"role": "system", "content": self.sys_prompt}]
        history = dataset.get(item={"user": self.user_id}).get("QwenPayload")
        if history is None:
            history = []
        history.append({"role": "user", "content": self.message})
        response = Generation.call(
            Generation.Models.qwen_max,
            messages=new + history,
            result_format='message'
        )
        try:
            # response = response
            history.append(response["output"]["choices"][0]["message"])
            item_id = dataset.queue({"user": self.user_id})
            dataset.set(item_id, "QwenPayload", history)
            return response["output"]["choices"][0]["message"]["content"]
        except:
            return response["message"]

    def ask_qwenvl(self) -> str:
        messages = []
        for i in self.raw_message:
            if type(i) is Segments.Text:
                messages.append({"text": str(i.get()).replace(".chat ", "", 1)})
            elif type(i) is Segments.Image:
                messages.append({"image": i.get()})
            else:
                messages.append({"text": str(i)})

        history = dataset.get(item={"user": self.user_id}).get("QwenVLPayload")
        if history is None:
            history = []
        history.append({"role": "user", "content": messages})
        response = MultiModalConversation.call(model=MultiModalConversation.Models.qwen_vl_chat_v1,
                                               messages=history)
        try:
            history.append(
                {"role": "assistant",
                 "content": [{"text": str(response["output"]["choices"][0]["message"]["content"])}]})
            item_id = dataset.queue({"user": self.user_id})
            dataset.set(item_id, "QwenVLPayload", history)
            result = response["output"]["choices"][0]["message"]["content"]
            return result
        except:
            return response["message"]


mode = "qwen"


class ModuleClass:
    def __init__(self, actions: Listener.Actions, event: Manager.Event):
        self.actions = actions
        self.event = event

    async def handle(self):
        if self.event.blocked or self.event.servicing:
            return
        dataset.load()
        global sys_prompt, mode
        # print(str(self.event.message))
        try:
            if str(self.event.message).startswith(".chat"):
                message = str(self.event.message).replace(".chat ", "", 1)
                # print(message)
                llm = LLM(self.event.user_id, message, self.event.message)
                text = llm.handle()
                # print(text)
                message = Manager.Message([Segments.Reply(self.event.message_id), Segments.Text(text)])
                self.actions.send(user_id=self.event.user_id, group_id=self.event.group_id, message=message)

            elif str(self.event.message).startswith(".sys") and self.event.is_owner:
                sys_prompt = str(self.event.message).replace(".sys ", "", 1)
                self.actions.send(user_id=self.event.user_id, group_id=self.event.group_id,
                                  message=Manager.Message(
                                      [
                                          Segments.Reply(self.event.message_id),
                                          Segments.Text("成功"),
                                      ]
                                  )
                                  )

            elif str(self.event.message).startswith(".mode") and self.event.is_owner:
                mode = str(self.event.message).replace(".mode ", "", 1)
                self.actions.send(user_id=self.event.user_id, group_id=self.event.group_id,
                                  message=Manager.Message(
                                      [
                                          Segments.Reply(self.event.message_id),
                                          Segments.Text("成功"),
                                      ]
                                  )
                                  )
        except AttributeError:
            return None
