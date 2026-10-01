import os.path
from io import BytesIO

import httpx
import meme_generator
from hyperot.v2 import Image, Message, Quote, Text
from hyperot.v2.events import MessageReceivedEvent
from meme_generator import exception
from typing_extensions import override

import ModuleClass
from ModuleClass import ModuleInfo, String

cmd = ".meme"


def _count_mismatch_text(kind: str, min_: int, max_: int, actual: int) -> str:
    if min_ == max_:
        return f"{kind}参数数量不正确，应当为{min_}，但实际为{actual}"
    return f"{kind}参数数量不正确，应当不少于{min_}，不多于{max_}，但实际为{actual}"


def get_meme(key: str) -> meme_generator.Meme:
    def f(x: meme_generator.Meme, key_word: str) -> bool:
        return key_word in x.keywords

    memes: list[meme_generator.Meme] = meme_generator.get_memes()
    res = [m for m in memes if f(m, key)]

    return res[0]


@ModuleClass.ModuleRegister.register(MessageReceivedEvent)
class Module(ModuleClass.Module[MessageReceivedEvent]):
    @override
    @staticmethod
    def info() -> ModuleInfo:
        return ModuleInfo(
            is_hidden=False,
            module_name="Memes",
            desc="制作表情包",
            helps="命令： .meme <keyword> <texts/images/args...>"
            "\n"
            "keyword：表情包模板对应的关键词；\n"
            "texts/images：表情包生成需要的文字、图片素材；\n"
            "args：参数：\n\n"
            "参数的传递： arg1=value1 arg2=value2 ...\n"
            "布尔值可以使用bool.1/bool.0表示，其他内容均被视为字符串"
            "\n"
            "\n可用的模板及关键词信息详见：https://harcicyang.github.io/hyper-bot/usage/qq_usage/memes_g/list.html",
        )

    @override
    async def handle(self) -> None:
        try:
            message = str(self.event.message)
        except AttributeError:
            return
        if not message.startswith(cmd):
            return

        try:
            keyword = message.split()[1].replace("[图片]", "")
            meme = get_meme(keyword)
        except Exception as e:
            if isinstance(e, exception.NoSuchMeme):
                text = (
                    f"找不到{message.split()[1].replace('[图片]', '')}这一模板，详见：\n"
                    "https://harcicyang.github.io/hyper-bot/usage/qq_usage/memes_g/list.html"
                )
            else:
                text = "https://harcicyang.github.io/hyper-bot/usage/qq_usage/memes_g/list.html"
            await self.api.scene(self.event.scene_type, self.event.scene_id).send(
                Message(Quote(message_id=str(self.event.message_id)), Text(text=text))
            )
            return

        texts: list[str] = []
        images: list[bytes] = []
        args: dict[str, bool | str | int | float] = {}
        n_msg = Message()
        for i in self.event.message:
            if isinstance(i, Text):
                n_msg = n_msg.add(i)
            elif isinstance(i, Image):
                source = i.source
                if source.startswith("http"):
                    response = httpx.get(source.replace("https://", "http://"), verify=False)
                    images.append(response.content)
                elif source.startswith("file://"):
                    with open(source[len("file://") :], "rb") as f:
                        images.append(f.read())

        for i in String(str(n_msg).replace(f".meme {keyword}", "")).cmdl_parse():
            if isinstance(i, String):
                texts.append(i)
            elif isinstance(i, dict):
                arg = list(i.values())[0]
                if "bool.1" in arg:
                    arg = True
                elif "bool.0" in arg:
                    arg = False
                args[list(i.keys())[0]] = arg

        # meme_generator 0.1.x：Meme 为可调用对象，成功返回 BytesIO，失败抛出 exception 子类异常。
        # 官方 .pyi 过时（描述为新版 generate API），故此处与 get_meme 均需忽略类型误报。
        try:
            result: BytesIO = meme(images=images, texts=texts, args=args)
        except exception.ImageNumberMismatch as e:
            text = _count_mismatch_text("图片", e.min_images, e.max_images, len(images))
        except exception.TextNumberMismatch as e:
            text = _count_mismatch_text("文字", e.min_texts, e.max_texts, len(texts))
        except exception.TextOverLength as e:
            text = f"文本过长: {e.text}"
        except exception.MemeFeedback as e:
            text = e.message
        except exception.ArgMismatch:
            text = "参数不正确"
        except exception.MemeGeneratorException as e:
            text = f"生成失败: {e}"
        else:
            meme_path = f"./temps/meme_{self.event.user_id}.png"
            with open(meme_path, "wb") as f:
                f.write(result.getvalue())
            content_text = f"file://{os.path.abspath(meme_path)}".replace("\\", "/")
            await self.api.scene(self.event.scene_type, self.event.scene_id).send(
                Message(Quote(message_id=str(self.event.message_id)), Image(source=content_text))
            )
            os.remove(meme_path)
            return

        await self.api.scene(self.event.scene_type, self.event.scene_id).send(
            Message(
                Quote(message_id=str(self.event.message_id)),
                Text(text=text),
                Text(text="\n详见: https://harcicyang.github.io/hyper-bot/usage/qq_usage/memes_g/list.html"),
            )
        )
