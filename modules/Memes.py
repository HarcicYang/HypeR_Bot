import os.path
from io import BytesIO
import httpx
import meme_generator
from meme_generator import exception

from hyperot import segments, common
import ModuleClass
from hyperot.events import *
from ModuleClass import ModuleInfo
from hyperot.utils.typextensions import String

cmd = ".meme"


def get_meme(key: str) -> meme_generator.Meme:
    def f(x: meme_generator.Meme, key_word: str) -> bool:
        if key_word in x.keywords:
            return True
        else:
            return False

    memes: list[meme_generator.Meme] = meme_generator.get_memes()
    res = filter(lambda x: f(x, key), memes)

    return list(res)[0]


@ModuleClass.ModuleRegister.register(GroupMessageEvent, PrivateMessageEvent)
class Module(ModuleClass.Module):
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
                  "\n可用的模板及关键词信息详见：https://harcicyang.github.io/hyper-bot/usage/qq_usage/memes_g/list.html"
        )

    async def handle(self):
        if self.event.blocked:
            return
        try:
            message = str(self.event.message)
        except AttributeError:
            return None
        if message.startswith(cmd):
            try:
                meme = get_meme(str(message).split()[1].replace("[图片]", ""))
            except:
                if len(str(message).split()) > 1:
                    await self.actions.send(
                        user_id=self.event.user_id,
                        group_id=self.event.group_id,
                        message=common.Message(
                            segments.Reply(self.event.message_id),
                            segments.Text(
                                f"找不到{str(message).split()[1].replace('[图片]', '')}这一模板，详见：\n"
                                f"https://harcicyang.github.io/hyper-bot/usage/qq_usage/memes_g/list.html"
                            )
                        )
                    )
                else:
                    await self.actions.send(
                        user_id=self.event.user_id,
                        group_id=self.event.group_id,
                        message=common.Message(
                            segments.Reply(self.event.message_id),
                            segments.Text(
                                "https://harcicyang.github.io/hyper-bot/usage/qq_usage/memes_g/list.html"
                            )
                        )
                    )
                return None
            texts = []
            images = []
            args = {}
            img_num = 0
            n_msg = common.Message()
            for i in self.event.message:
                if type(i) is segments.Text:
                    n_msg.add(i)
                elif type(i) is segments.Image:
                    if str(i.file).startswith("http"):
                        response = httpx.get(i.file, verify=False)
                    else:
                        response = httpx.get(i.url, verify=False)
                    with open(f"./temps/img{img_num}_{self.event.user_id}.jpg", "wb") as f:
                        f.write(response.content)
                    images.append(f"./temps/img{img_num}_{self.event.user_id}.jpg")
                    img_num += 1

            for i in String(
                    str(n_msg).replace(f".meme {str(message).split()[1].replace('[图片]', '')}", "")
            ).cmdl_parse():
                if isinstance(i, String):
                    texts.append(i)
                elif isinstance(i, dict):
                    arg = list(i.values())[0]
                    if "bool.1" in arg:
                        arg = True
                    elif "bool.0" in arg:
                        arg = False
                    args[list(i.keys())[0]] = arg

            has_error = False

            try:
                result: BytesIO = meme(images=images, texts=texts, args=args)

            except exception.TextNumberMismatch:
                if meme.params_type.min_texts == meme.params_type.max_texts:
                    text = f"文字参数数量不正确，应当为{meme.params_type.min_texts}，但实际为{len(texts)}"
                else:
                    text = f"文字参数数量不正确，应当不少于{meme.params_type.min_texts}，不多于{meme.params_type.max_texts}，但实际为{len(texts)}"
                has_error = True

            except exception.ImageNumberMismatch:
                if meme.params_type.min_images == meme.params_type.max_images:
                    text = f"图片参数数量不正确，应当为{meme.params_type.min_images}，但实际为{len(images)}"
                else:
                    text = f"图片参数数量不正确，应当不少于{meme.params_type.min_images}，不多于{meme.params_type.max_images}，但实际为{len(images)}"
                has_error = True

            except exception.ArgMismatch:
                text = "参数不正确"
                has_error = True

            except exception.TextOverLength as e:
                text = f"文本过长: {e}"
                has_error = True

            if has_error:
                message = common.Message(
                    segments.Reply(self.event.message_id),
                    segments.Text(text),
                    segments.Text(
                        "\n详见: https://harcicyang.github.io/hyper-bot/usage/qq_usage/memes_g/list.html")
                )
                await self.actions.send(user_id=self.event.user_id, group_id=self.event.group_id, message=message)
                return

            else:
                content = result.getvalue()
                with open(f"./temps/meme_{self.event.user_id}.png", "wb") as f:
                    f.write(content)
                content_text = f"file://{os.path.abspath(f'./temps/meme_{self.event.user_id}.png')}"

                await self.actions.send(
                    user_id=self.event.user_id,
                    group_id=self.event.group_id,
                    message=common.Message(
                        segments.Reply(self.event.message_id),
                        segments.Image(content_text)
                    )
                )
                os.remove(f"./temps/meme_{self.event.user_id}.png")
                for i in images:
                    os.remove(i)
