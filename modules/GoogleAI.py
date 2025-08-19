from typing import Union
from google import genai
from google.genai import types as genai_types
import httpx
import filetype


class Parts:
    @staticmethod
    class File:
        def __init__(self, file: genai_types.File):
            self.file = file

        @classmethod
        def upload_from_file(cls, path: str, cli: genai.Client):
            with open(path, "rb") as f:
                mime = filetype.guess(f.read()).mime
            file = cli.files.upload(path=path, config=genai_types.UploadFileConfig(mime_type=mime))
            return cls(file)

        @classmethod
        def upload_from_url(cls, url: str, cli: genai.Client):
            response = httpx.get(url, verify=False)
            path = f"./temps/google_{len(response.content)}_{len(url)}"
            with open(path, "wb") as f:
                f.write(response.content)
            return cls.upload_from_file(path, cli)

        def to_raw(self) -> genai_types.File:
            return self.file

    @staticmethod
    class Text:
        def __init__(self, text: str):
            self.text = text

        def to_raw(self) -> str:
            return self.text


class BaseRole:
    def __init__(self, *args: Union[Parts.File, Parts.Text]):
        self.content = list(args)
        self.tag = "none"

    def res(self) -> list:
        return [i.to_raw() for i in self.content]


class Roles:
    @staticmethod
    class User(BaseRole):
        def __init__(self, *args: Union[Parts.File, Parts.Text]):
            super().__init__(*args)
            self.tag = "user"

    @staticmethod
    class Model(BaseRole):
        def __init__(self, *args: Union[Parts.File, Parts.Text]):
            super().__init__(*args)
            self.tag = "model"


class Context:
    def __init__(self, model: genai.Client, cfg: genai_types.GenerateContentConfig):
        self.cli = model
        self.cfg = cfg
        self.chat = self.cli.chats.create(model="gemini-2.5-flash", config=self.cfg)

    def gen_content(self, content: Roles.User) -> str:
        try:
            # new = self.__gen_content(content)
            # res = self.model.generate_content(contents=new, safety_settings=self.safety)
            res = self.chat.send_message(content.res())
            return res.text
        except Exception as e:
            raise e
