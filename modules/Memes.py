import os.path
from io import BytesIO

import httpx
import meme_generator
from hyperot import common, segments
from hyperot.events import *
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
    # 官方 .pyi 过时：运行时 keywords 是 Meme 的直接属性（.pyi 误写为 info.keywords）。
    def f(x: meme_generator.Meme, key_word: str) -> bool:
        return key_word in x.keywords  # pyrefly: ignore[missing-attribute]

    memes: list[meme_generator.Meme] = meme_generator.get_memes()
    res = filter(lambda x: f(x, key), memes)  # pyrefly: ignore[implicit-any-lambda]

    return list(res)[0]


@ModuleClass.ModuleRegister.register(GroupMessageEvent, PrivateMessageEvent)
class Module(ModuleClass.Module[GroupMessageEvent | PrivateMessageEvent]):
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
        if self.event.blocked:
            return
        try:
            message = str(self.event.message)
        except AttributeError:
            return
        if not message.startswith(cmd):
            return

        try:
            keyword = message.split()[1].replace("[图片]", "")
            meme = get_meme(keyword)
        except Exception:
            if len(message.split()) > 1:
                await self.actions.send_msg(
                    user_id=self.event.user_id,
                    group_id=self.event.group_id,
                    message=common.Message(
                        segments.Reply(self.event.message_id),
                        segments.Text(
                            f"找不到{message.split()[1].replace('[图片]', '')}这一模板，详见：\n"
                            f"https://harcicyang.github.io/hyper-bot/usage/qq_usage/memes_g/list.html"
                        ),
                    ),
                )
            else:
                await self.actions.send_msg(
                    user_id=self.event.user_id,
                    group_id=self.event.group_id,
                    message=common.Message(
                        segments.Reply(self.event.message_id),
                        segments.Text("https://harcicyang.github.io/hyper-bot/usage/qq_usage/memes_g/list.html"),
                    ),
                )
            return

        texts: list[str] = []
        images: list[bytes] = []
        args: dict[str, bool | str | int | float] = {}
        n_msg = common.Message()
        for i in self.event.message:
            if type(i) is segments.Text:
                n_msg.add(i)
            elif type(i) is segments.Image:
                file = i.file if i.file.startswith("http") else i.url
                if file is None:
                    continue
                response = httpx.get(file.replace("https://", "http://"), verify=False)
                images.append(response.content)

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
            result: BytesIO = meme(images=images, texts=texts, args=args)  # pyrefly: ignore[not-callable]
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
            with open(f"./temps/meme_{self.event.user_id}.png", "wb") as f:
                f.write(result.getvalue())
            content_text = f"file://{os.path.abspath(f'./temps/meme_{self.event.user_id}.png')}".replace("\\", "/")
            await self.actions.send_msg(
                user_id=self.event.user_id,
                group_id=self.event.group_id,
                message=common.Message(segments.Reply(self.event.message_id), segments.Image(content_text)),
            )
            os.remove(f"./temps/meme_{self.event.user_id}.png")
            return

        await self.actions.send_msg(
            user_id=self.event.user_id,
            group_id=self.event.group_id,
            message=common.Message(
                segments.Reply(self.event.message_id),
                segments.Text(text),
                segments.Text("\n详见: https://harcicyang.github.io/hyper-bot/usage/qq_usage/memes_g/list.html"),
            ),
        )
