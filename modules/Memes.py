import os.path
import traceback
from io import BytesIO

import httpx
from Hyper import Manager, ModuleClass, Segments
import meme_generator
from meme_generator import exception

from Hyper.ModuleClass import ModuleInfo

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


@ModuleClass.ModuleRegister.register(["message"])
class Module(ModuleClass.Module):
    @staticmethod
    def info() -> ModuleInfo:
        return ModuleInfo(
            is_hidden=False,
            module_name="Memes",
            desc="制作表情包",
            helps="命令： .meme <keyword> <texts/images...> {args...}"
                  "\n"
                  "keyword：表情包模板对应的关键词；\n"
                  "texts/images：表情包生成需要的文字、图片素材；\n"
                  "args：参数：\n\n"
                  "参数的传递： {arg1=value1,arg2=value2,...}\n"
                  "布尔值可以使用bool.1/bool.0表示，其他内容均被视为字符串"
        )

    async def handle(self):
        if self.event.blocked or self.event.servicing:
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
                    await self.actions.send(user_id=self.event.user_id, group_id=self.event.group_id,
                                            message=Manager.Message(
                                                [
                                                    Segments.Reply(self.event.message_id),
                                                    Segments.Text(
                                                        f"找不到{str(message).split()[1].replace('[图片]', '')}这一模板，详见：\n"
                                                        f"https://github.com/MeetWq/meme-generator/wiki/%E8%A1%A8%E6%83%85%E5%88%97%E8%A1%A8"
                                                    )
                                                ]
                                            )
                                            )
                else:
                    await self.actions.send(user_id=self.event.user_id, group_id=self.event.group_id,
                                            message=Manager.Message(
                                                [
                                                    Segments.Reply(self.event.message_id),
                                                    Segments.Text(
                                                        "https://github.com/MeetWq/meme-generator/wiki/%E8%A1%A8%E6%83%85%E5%88%97%E8%A1%A8"
                                                    )
                                                ]
                                            )
                                            )
                return None
            texts = []
            images = []
            args = {}
            img_num = 0
            for i in self.event.message:
                if type(i) is Segments.Text:
                    i = str(i).replace(f"{cmd} ", "", 1).replace(str(message).split()[1], "")
                    listed = i.split()
                    for j in listed:
                        if "{" in j and "}" in j:
                            j = j.replace("{", "").replace("}", "")
                            argv = j.split("=")
                            if "bool" in argv[1]:
                                if "1" in argv[1] or "true" in argv[1].lower():
                                    value = True
                                else:
                                    value = False
                            else:
                                value = argv[1]
                            args[argv[0]] = value
                        else:
                            texts.append(j)
                elif type(i) is Segments.Image:
                    if str(i.file).startswith("http"):
                        response = httpx.get(i.file)
                    else:
                        response = httpx.get(i.url)
                    with open(f"./temps/img{img_num}.jpg", "wb") as f:
                        f.write(response.content)
                    images.append(f"./temps/img{img_num}.jpg")
                    img_num += 1
            has_error = False

            try:
                result: BytesIO = await meme(images=images, texts=texts, args=args)

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
                text = f"文本“{e.text}”过长"

            if has_error:
                message = Manager.Message(
                    [
                        Segments.Reply(self.event.message_id),
                        Segments.Text(text),
                        Segments.Text(
                            "\n详见: https://github.com/MeetWq/meme-generator/wiki/%E8%A1%A8%E6%83%85%E5%88%97%E8%A1%A8")
                    ]
                )
                await self.actions.send(user_id=self.event.user_id, group_id=self.event.group_id, message=message)
                return

            else:
                content = result.getvalue()
                with open("./temps/meme.png", "wb") as f:
                    f.write(content)
                content_text = f"file://{os.path.abspath('./temps/meme.png')}"

                await self.actions.send(user_id=self.event.user_id, group_id=self.event.group_id,
                                        message=Manager.Message(
                                            [
                                                Segments.Reply(self.event.message_id),
                                                # Segments.Image("file://" + os.path.abspath("result.png"))
                                                Segments.Image(content_text)
                                            ]
                                        )
                                        )
