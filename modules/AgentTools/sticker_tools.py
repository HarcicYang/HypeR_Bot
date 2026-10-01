"""表情包工具：检索、发送、添加、删除全局表情包库。

表情包库是全局共享的单例（所有群/私聊/用户共用一个库，不区分用户），每张表情包
都带有 Gemini 生成的画面/情绪摘要。除 `.ag.stk` 命令外，Agent 也可以直接调用
sticker_add / sticker_delete 维护库内容；表情包库不设权限分级，任何用户的消息
都可以触发增删。
"""

import asyncio
import json
import os
import time

from hyperot import configurator
from hyperot.v2 import Image, Message

from modules.AgentRuntime.sticker_store import collect_sticker, get_sticker_store
from modules.AgentTools.registry import AgentToolBase, ToolContext, tool

config = configurator.BotConfig.get("hyper-bot")

# 每个会话的最近发送时刻，key = "{ev_type}:{scene_id}"；防止表情包刷屏
LAST_SENT: dict[str, float] = {}


def _cooldown_left(scene_key: str) -> float:
    interval = float(config.others.get("agent_sticker_send_interval") or 10)
    if interval <= 0:
        return 0.0
    return max(0.0, interval - (time.time() - LAST_SENT.get(scene_key, 0.0)))


class StickerTools(AgentToolBase):
    @tool(group="sticker", scenes=("group", "private"))
    async def sticker_add(self, ctx: ToolContext, url: str, keywords: str = "") -> str:
        """收藏一张图片到全局表情包库，Gemini 自动生成描述摘要。

        - url: 图片的下载链接（消息上报中的图片 url，与 read_image 的取法一致）
        - keywords: 可选关键词，空格分隔，辅助检索

        重复图片（md5 相同）直接返回已存在的条目；表情包库不设权限分级，
        任何用户要求收藏图片时都应当执行。
        """
        entry = await collect_sticker(url, keywords, ctx.principal_id or 0)
        if "error" in entry:
            return f"收藏失败：{entry['error']}"
        if entry.get("duplicate"):
            return f"这张图片已收藏为表情包 #{entry.get('id')}，描述:{entry.get('desc') or '(无)'}"
        return (
            f"已收藏为表情包 #{entry.get('id')}\n"
            f"描述:{entry.get('desc') or '(无)'}\n"
            f"关键词:{entry.get('keywords') or '(无)'}"
        )

    @tool(group="sticker", scenes=("group", "private"))
    async def sticker_delete(self, ctx: ToolContext, sticker_id: int) -> str:
        """从全局表情包库删除指定 id 的表情包（库内所有用户共享，不区分收藏者）。

        - sticker_id: sticker_search 或 sticker_list 返回的表情包 id
        """
        store = get_sticker_store()
        removed = await asyncio.to_thread(store.delete_sticker, sticker_id)
        if removed is None:
            return f"表情包 #{sticker_id} 不存在，可用 sticker_list 查看已有表情包"
        return f"表情包 #{sticker_id} 已删除"

    @tool(group="sticker", scenes=("group", "private"))
    async def sticker_search(self, ctx: ToolContext, query: str, top_k: int = 5) -> str:
        """按画面、情绪或用途检索表情包库，返回候选列表（id、描述、关键词、收藏者）。

        - query: 画面或情绪描述，如“猫猫震惊”“无语摆烂”“幸灾乐祸”；支持同义改写
        - top_k: 返回数量，1-10

        没有合适的候选就不要硬发；发送用 sticker_send(sticker_id)。
        """
        top_k = max(1, min(top_k, 10))
        store = get_sticker_store()
        items = await asyncio.to_thread(store.search, query, top_k)
        return json.dumps({"items": items, "total": store.count()}, ensure_ascii=False)

    @tool(group="sticker", scenes=("group", "private"))
    async def sticker_send(self, ctx: ToolContext, sticker_id: int) -> str:
        """把指定 id 的表情包图片原样发送到当前会话（不带任何解释文字）。

        - sticker_id: sticker_search 或 sticker_list 返回的表情包 id
        """
        store = get_sticker_store()
        entry = store.get(sticker_id)
        if entry is None:
            return f"表情包 #{sticker_id} 不存在，先用 sticker_search 检索"
        path = str(entry.get("file") or "")
        if not path or not os.path.isfile(path):
            return f"表情包 #{sticker_id} 的图片文件缺失，换一张试试"
        scene_key = f"{ctx.ev_type}:{ctx.scene_id}"
        left = _cooldown_left(scene_key)
        if left > 0:
            return f"表情包发送太频繁，约 {int(left) + 1} 秒后再试"
        message = Message(Image(source="file://" + os.path.abspath(path)))
        if ctx.ev_type == "group":
            result = await ctx.actions.group(str(ctx.scene_id)).send(message)
        else:
            result = await ctx.actions.user(str(ctx.scene_id)).send(message)
        LAST_SENT[scene_key] = time.time()
        return f"表情包 #{sticker_id} 已发送：message_id={result.message_id}"

    @tool(group="sticker", scenes=("group", "private"))
    async def sticker_list(self, ctx: ToolContext, limit: int = 10) -> str:
        """按收藏时间倒序列出表情包库条目（id、描述、关键词、收藏者），用于了解库内有什么。"""
        limit = max(1, min(limit, 30))
        store = get_sticker_store()
        items = await asyncio.to_thread(store.list_recent, limit)
        return json.dumps({"items": items, "total": store.count()}, ensure_ascii=False)
