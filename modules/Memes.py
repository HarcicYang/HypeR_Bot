import httpx
from lib import Manager, Listener, Segements
from meme_generator import get_meme
import os

emoji_dict = {
    "兆": "5000choyen",
    "二次元入口": "acg_entrance",
    "添乱": "add_chaos",
    "给社会添乱": "add_chaos",
    "上瘾": "addiction",
    "毒瘾发作": "addiction",
    "一样": "alike",
    "一直": "always",
    "我永远喜欢": "always_like",
    "防诱拐": "anti_kidnap",
    "阿尼亚喜欢": "anya_suki",
    "鼓掌": "applaud",
    "升天": "ascension",
    "问问": "ask",
    "继续干活": "back_to_work",
    "打工人": "back_to_work",
    "悲报": "bad_news",
    "拍头": "beat_head",
    "啃": "bite",
    "高血压": "blood_pressure",
    "蔚蓝档案标题": "bluearchive",
    "batitle": "bluearchive",
    "波奇手稿": "bocchi_draft",
    "布洛妮娅举牌": "bronya_holdsign",
    "大鸭鸭举牌": "bronya_holdsign",
    "奶茶": "bubble_tea",
    "遇到困难请拨打": "call_110",
    "草神啃": "caoshen_bite",
    "咖波画": "capoo_draw",
    "咖波撕": "capoo_rip",
    "咖波贴": "capoo_rub",
    "咖波说": "capoo_say",
    "咖波撞": "capoo_strike",
    "舰长": "captain",
    "奖状": "certificate",
    "证书": "certificate",
    "馋身子": "chanshenzi",
    "字符画": "charpic",
    "追火车": "chase_train",
    "国旗": "china_flag",
    "小丑": "clown",
    "迷惑": "confuse",
    "兑换券": "coupon",
    "捂脸": "cover_face",
    "爬": "crawl",
    "群青": "cyan",
    "白天黑夜": "daynight",
    "像样的亲亲": "decent_kiss",
    "典中典": "dianzhongdian",
    "恐龙": "dinosaur",
    "注意力涣散": "distracted",
    "离婚协议": "divorce",
    "离婚申请": "divorce",
    "狗都不玩": "dog_dislike",
    "管人痴": "dog_of_vtb",
    "不要靠近": "dont_go_near",
    "别碰": "dont_touch",
    "douyin": "douyin",
    "吃": "eat",
    "狂爱": "fanatic",
    "击剑": "fencing",
    "满脑子": "fill_head",
    "整点薯条": "find_chips",
    "闪瞎": "flash_blind",
    "关注": "follow",
    "芙莉莲拿": "frieren_take",
    "哈哈镜": "funny_mirror",
    "垃圾桶": "garbage",
    "原神启动": "genshin_start",
    "喜报": "good_news",
    "google": "google",
    "鬼畜": "guichu",
    "手枪": "gun",
    "锤": "hammer",
    "低情商xx高情商xx": "high_EQ",
    "打穿/打穿屏幕": "hit_screen",
    "记仇": "hold_grudge",
    "抱紧": "hold_tight",
    "抱大腿": "hug_leg",
    "胡桃啃": "hutao_bite",
    "坐牢": "imprison",
    "不文明": "incivilization",
    "采访": "interview",
    "急急国王": "jiji_king",
    "啾啾": "jiujiu",
    "万花筒": "kaleidoscope",
    "凯露指": "karyl_point",
    "远离": "keep_away",
    "踢球": "kick_ball",
    "卡比锤": "kirby_hammer",
    "亲亲": "kiss",
    "可莉吃": "klee_eat",
    "敲": "knock",
    "偷学": "learn",
    "等价无穷小": "lim_x_0",
    "听音乐": "listen_music",
    "小天使": "little_angel",
    "加载中": "loading",
    "看扁": "look_flat",
    "看图标": "look_this_icon",
    "寻狗启事": "lost_dog",
    "永远爱你": "love_you",
    "罗永浩说": "luoyonghao_say",
    "鲁迅说": "luxun_say",
    "麦克阿瑟说": "maikease",
    "旅行伙伴觉醒": "maimai_awaken",
    "旅行伙伴加入": "maimai_join",
    "交个朋友": "make_friend",
    "结婚申请": "marriage",
    "结婚登记": "marriage",
    "流星": "meteor",
    "米哈游": "mihoyo",
    "上香": "mourning",
    "低语": "murmur",
    "我朋友说": "my_friend",
    "我老婆": "my_wife",
    "亚文化取名机": "name_generator",
    "你可能需要": "need",
    "猫猫举牌": "nekoha_holdsign",
    "你好骚啊": "nihaosaoa",
    "虹夏举牌": "nijika_holdsign",
    "无响应": "no_response",
    "有内鬼": "nokia",
    "不喊我": "not_call_me",
    "请假条": "note_for_leave",
    "我推的网友": "oshi_no_ko",
    "osu": "osu",
    "加班": "overtime",
    "这像画吗": "paint",
    "小画家": "painter",
    "甩锅": "pass_the_buck",
    "拍": "pat",
    "完美": "perfect",
    "摸": "petpet",
    "捏": "pinch",
    "玩": "play",
    "玩游戏": "play_game",
    "出警": "police",
    "警察": "police1",
    "pornhub": "pornhub",
    "土豆": "potato",
    "捣": "pound",
    "打印": "printing",
    "舔": "prpr",
    "可达鸭": "psyduck",
    "打拳": "punch",
    "切格瓦拉": "qiegewala",
    "举": "raise_image",
    "举牌": "raise_sign",
    "看书": "read_book",
    "复读": "repeat",
    "撕": "rip",
    "怒撕": "rip_angrily",
    "诈尸": "rise_dead",
    "滚": "roll",
    "贴贴": "rub",
    "快跑": "run",
    "安全感": "safe_sense",
    "挠头": "scratch_head",
    "刮刮乐": "scratchcard",
    "滚屏": "scroll",
    "食屎啦你": "shishilani",
    "震惊": "shock",
    "谁反对": "shuifandui",
    "别说了": "shutup",
    "坐得住": "sit_still",
    "坐的住": "sit_still",
    "一巴掌": "slap",
    "口号": "slogan",
    "砸": "smash",
    "踩": "step_on",
    "炖": "stew",
    "吸": "suck",
    "精神支柱": "support",
    "对称": "symmetric",
    "唐可可举牌": "tankuku_raisesign",
    "嘲讽": "taunt",
    "讲课": "teach",
    "拿捏": "tease",
    "望远镜": "telescope",
    "想什么": "think_what",
    "这是鸡": "this_chicken",
    "丢": "throw",
    "抛": "throw_gif",
    "捶": "thump",
    "捶爆": "thump_wildly",
    "紧紧贴着": "tightly",
    "紧贴": "tightly",
    "一起": "together",
    "汤姆嘲笑": "tom_tease",
    "上坟": "tomb_yeah",
    "坟前比耶": "tomb_yeah",
    "恍惚": "trance",
    "转": "turn",
    "搓": "twist",
    "万能表情": "universal",
    "空白表情": "universal",
    "震动": "vibrate",
    "xx起来了": "wakeup",
    "墙纸": "wallpaper",
    "胡桃平板": "walnut_pad",
    "胡桃放大": "walnut_zoom",
    "王境泽": "wangjingze",
    "洗衣机": "washer",
    "波纹": "wave",
    "为所欲为": "weisuoyuwei",
    "我想上的": "what_I_want_to_do",
    "最想要的东西": "what_he_wants",
    "为什么@我": "why_at_me",
    "为什么要有手": "why_have_hands",
    "风车转": "windmill_turn",
    "许愿失败": "wish_fail",
    "木鱼": "wooden_fish",
    "膜": "worship",
    "膜拜": "worship",
    "吴京xx中国xx": "wujing",
    "五年怎么过的": "wunian",
    "压力大爷": "yalidaye",
    "yt": "youtube",
    "youtube": "youtube",
    "曾小贤": "zengxiaoxian",
}

cmd = ".meme"


class ModuleClass:
    def __init__(self, actions: Listener.Actions, event: Manager.Event):
        self.actions = actions
        self.event = event

    async def handle(self):
        try:
            message = str(self.event.message)
        except AttributeError:
            return None
        if message.startswith(cmd):
            try:
                meme = get_meme(emoji_dict[str(message).split()[1]])
            except:
                self.actions.send(user_id=self.event.user_id, group_id=self.event.group_id,
                                  message=Manager.Message(
                                      [
                                          Segements.Text(
                                              "参数错误。请参阅https://github.com/MeetWq/meme-generator/blob/main/docs/memes.md"
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
                if type(i) is Segements.Text:
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
                elif type(i) is Segements.Image:
                    response = httpx.get(i.get())
                    with open(f"img{img_num}.jpg", "wb") as f:
                        f.write(response.content)
                    images.append(f"img{img_num}.jpg")
                    img_num += 1
            result = await meme(images=images, texts=texts, args=args)
            with open("result.png", "wb") as f:
                f.write(result.getvalue())

            self.actions.send(user_id=self.event.user_id, group_id=self.event.group_id,
                              message=Manager.Message(
                                  [
                                      Segements.Reply(self.event.message_id),
                                      Segements.Image("file:///" + os.path.abspath("result.png"))
                                  ]
                              )
                              )
