import os.path
import httpx
from Hyper import Manager, ModuleClass, Segments
import meme_generator

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
    async def handle(self):
        if self.event.blocked or self.event.servicing:
            return
        try:
            message = str(self.event.message)
        except AttributeError:
            return None
        if message.startswith(cmd):
            try:
                meme = get_meme(str(message).split()[1])
            except:
                await self.actions.send(user_id=self.event.user_id, group_id=self.event.group_id,
                                        message=Manager.Message(
                                            [
                                                Segments.Text(
                                                    r"https://github.com/MeetWq/meme-generator/wiki/%E8%A1%A8%E6%83%85%E5%88%97%E8%A1%A8"
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
                    response = httpx.get(i.get())
                    with open(f"img{img_num}.jpg", "wb") as f:
                        f.write(response.content)
                    images.append(f"img{img_num}.jpg")
                    img_num += 1
            result = await meme(images=images, texts=texts, args=args)
            # with open("result.png", "wb") as f:
            #     f.write(result.getvalue())
            content = result.getvalue()
            with open("meme.png", "wb") as f:
                f.write(content)
            content_text = os.path.abspath("meme.png")

            await self.actions.send(user_id=self.event.user_id, group_id=self.event.group_id,
                                    message=Manager.Message(
                                        [
                                            Segments.Reply(self.event.message_id),
                                            # Segments.Image("file://" + os.path.abspath("result.png"))
                                            Segments.Image(content_text)

                                        ]
                                    )
                                    )
