import os.path
from typing import override

import httpx
import meme_generator
from hyperot import common, segments
from hyperot.events import *

import ModuleClass
from ModuleClass import ModuleInfo, String

cmd = ".meme"


def get_meme(key: str) -> meme_generator.Meme:
    def f(x: meme_generator.Meme, key_word: str) -> bool:
        return key_word in x.info.keywords

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
        images: list[tuple[str, bytes]] = []
        args: dict[str, bool | str | int | float] = {}
        img_num = 0
        n_msg = common.Message()
        for i in self.event.message:
            if type(i) is segments.Text:
                n_msg.add(i)
            elif type(i) is segments.Image:
                file = i.file if i.file.startswith("http") else i.url
                if file is None:
                    continue
                response = httpx.get(file.replace("https://", "http://"), verify=False)
                images.append((f"img{img_num}.jpg", response.content))
                img_num += 1

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

        # 运行时为编译版扩展，签名是 generate(images, texts, options)；官方 .pyi 已过时（误写为 text）。
        result = meme.generate(images=images, texts=texts, options=args)  # pyrefly: ignore[missing-argument, unexpected-keyword]

        if isinstance(result, bytes):
            with open(f"./temps/meme_{self.event.user_id}.png", "wb") as f:
                f.write(result)
            content_text = f"file://{os.path.abspath(f'./temps/meme_{self.event.user_id}.png')}".replace("\\", "/")
            await self.actions.send_msg(
                user_id=self.event.user_id,
                group_id=self.event.group_id,
                message=common.Message(segments.Reply(self.event.message_id), segments.Image(content_text)),
            )
            os.remove(f"./temps/meme_{self.event.user_id}.png")
            return

        if isinstance(result, (meme_generator.ImageNumberMismatch, meme_generator.TextNumberMismatch)):
            if result.min == result.max:
                kind = "图片" if isinstance(result, meme_generator.ImageNumberMismatch) else "文字"
                text = f"{kind}参数数量不正确，应当为{result.min}，但实际为{result.actual}"
            else:
                kind = "图片" if isinstance(result, meme_generator.ImageNumberMismatch) else "文字"
                text = f"{kind}参数数量不正确，应当不少于{result.min}，不多于{result.max}，但实际为{result.actual}"
        elif isinstance(result, meme_generator.TextOverLength):
            text = f"文本过长: {result.text}"
        elif isinstance(result, meme_generator.MemeFeedback):
            text = result.feedback
        else:
            text = "生成失败"

        await self.actions.send_msg(
            user_id=self.event.user_id,
            group_id=self.event.group_id,
            message=common.Message(
                segments.Reply(self.event.message_id),
                segments.Text(text),
                segments.Text("\n详见: https://harcicyang.github.io/hyper-bot/usage/qq_usage/memes_g/list.html"),
            ),
        )
