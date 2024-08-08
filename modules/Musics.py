from Hyper.Events import GroupMessageEvent
from Hyper.ModuleClass import ModuleInfo, ModuleRegister, Module
from Hyper.Segments import *
from Hyper.Manager import Message
from Hyper.Utils.Logic import Downloader

from pyncm import apis
import os
import hashlib


def distance(s1: str, s2: str) -> int:
    if s2 > s1:
        s1, s2 = s2, s1

    difference = 0
    s2 += " " * (len(s1) - len(s2))
    for i in range(len(s1)):
        if s1[i] != s2[i]:
            difference += 1

    return difference


def string_similarity(s1: str, s2: str) -> float:
    try:
        similarity = 1 - distance(s1, s2) / max(len(s1), len(s2))
    except:
        return 1.0
    return similarity


def sim_sort(songs_list: list, reference: str) -> list:
    distances = [(i, -string_similarity(i["al"]["name"], reference)) for i in songs_list]

    sorted_songs = sorted(distances, key=lambda x: x[1])

    return [i for i, _ in sorted_songs]


def search(name: str, num: int = 15) -> list:
    res = apis.cloudsearch.GetSearchResult(name, limit=num)
    songs: list = sim_sort(res["result"]["songs"], name)
    result = []

    for i in songs:
        artists = " / "
        ar_list = []
        for j in i["ar"]:
            ar_list.append(j["name"])
        ar = artists.join(ar_list)
        result.append(f"{i['id']}: {i['name']} - {ar}")

    return result


async def download(song_id: int) -> tuple[bool, str, str]:
    res = apis.track.GetTrackAudioV1([song_id])
    url = res["data"][0]["url"]
    if url is None:
        return False, "无法获取歌曲URL，这可能是一个付费歌曲或该歌曲不存在", ""
    md5 = res["data"][0]["md5"]
    suffix = res["data"][0]["type"]
    did = 0
    try:
        while did <= 5:
            dlr = Downloader(
                url,
                f"./temps/music_{song_id}.{suffix}",
                threads=20,
                silent=True
            )
            await dlr.download()
            with open(f"./temps/music_{song_id}.{suffix}", "rb") as f:
                music_data = f.read()
                readable_hash = hashlib.md5(music_data).hexdigest()

            if readable_hash == md5:
                break
            else:
                did += 1
    except Exception as e:
        return False, f"出现错误：{e}", ""

    if did >= 5:
        return False, "下载校验不通过", ""

    return True, "", os.path.abspath(f"./temps/music_{song_id}.{suffix}")


@ModuleRegister.register(GroupMessageEvent)
class Musics(Module):
    @staticmethod
    def info() -> ModuleInfo:
        return ModuleInfo(
            is_hidden=False,
            module_name="Netease Musics",
            desc="自助点歌",
            helps="命令： .music <search/play> <name/num>\n\n"
                  "search: 进行搜索操作\n"
                  "name: 搜索的歌曲名\n"
                  "play: 进行播放操作\n"
                  "num: 要播放的音乐在搜索列表中的序号"
        )

    async def handle(self):
        if len(self.event.message) == 0:
            return
        if (
                str(self.event.message).startswith(".music") or
                (
                        isinstance(self.event.message[0], At) and
                        str(self.event.message[0].qq) == str(self.event.self_id)
                )
        ):
            cmd = str(self.event.message).split(" ", maxsplit=2)
            action = cmd[1]
            if action == "search":
                res_list = search(cmd[2])
                rec_list = res_list[:5]
                res_word = "搜索结果：\n\n" + "\n".join(res_list) + "\n\n冒号前为该歌曲的id，若要播放，请使用如下命令：\n.music play 歌曲id"

                msg = Message(Reply(self.event.message_id), Text(res_word))
                await self.actions.send(group_id=self.event.group_id, message=msg)
                custom_row = []
                for i in rec_list:
                    custom_row.append(
                        KeyBoardRow(
                            [
                                KeyBoardButton(
                                    text=i.split(" - ")[0].split(": ")[1],
                                    data=f"ncm_qa_play {i.split(' - ')[0].split(': ')[0]}",
                                    enter=True
                                ),
                            ]
                        )
                    )

                await self.actions.send(group_id=self.event.group_id, message=Message(KeyBoard(custom_row)))

            elif action == "play" or "ncm_qa_play":
                song_id = int(cmd[2])
                msg_res = await self.actions.send(
                    group_id=self.event.group_id,
                    message=Message(
                        Reply(self.event.message_id),
                        Text("正在获取歌曲，请稍等")
                    )
                )
                msg_id = msg_res.data["message_id"]
                res = await download(song_id)
                if res[0]:
                    path = res[2]
                    msg = Message(Record(path))
                    await self.actions.send(group_id=self.event.group_id, message=msg)
                    await self.actions.del_message(message_id=msg_id)
                    os.remove(path)
                else:
                    err_msg = res[1]
                    await self.actions.del_message(message_id=msg_id)
                    msg = Message(Reply(self.event.message_id), Text(err_msg))
                    await self.actions.send(group_id=self.event.group_id, message=msg)
