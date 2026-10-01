"""表情包库：群友上传的表情图片 + Gemini 生成的检索用描述摘要。

数据层架在 MemoryStore 之上：每张表情包就是一条记忆条目（text 为「关键词 + 描述」），
条目额外携带 file / adder / md5 等元数据（MemoryStore 的 JSON 持久化原样保留额外字段），
从而直接获得 BGE 向量 + BM25 双臂 RRF 混合检索，以及 fastembed 不可用时的降级路径。

存储布局（基座 path = ./temps/agent_stickers/stickers）：
- stickers.json / stickers.npz —— 条目与向量（MemoryStore 约定）
- stickers.files/{md5}.{ext}   —— 图片原文件，按内容寻址，天然去重

线程约定与 memory_store 相同：增删是阻塞调用（含 embedding），调用方用
asyncio.to_thread 包裹；检索为纯读，可直接调用。
"""

import asyncio
import contextlib
import hashlib
import os
from typing import Any, cast

from hyperot import configurator

from modules.AgentTools.memory_store import MemoryStore

config = configurator.BotConfig.get("hyper-bot")

STICKERS_DIR = "./temps/agent_stickers"
STICKERS_PATH = os.path.join(STICKERS_DIR, "stickers")
DESC_MAX_CHARS = 200
INDEX_TEXT_MAX = 500

STICKER_DESCRIBE_PROMPT = """请描述这张表情包图片，供之后按画面和情绪检索。用简体中文，100 字以内，一整段话，不要分点、不要寒暄。

需要覆盖：
1. 画面主体（角色、动物或物体；图中出现的文字原样保留）；
2. 动作、表情与整体情绪氛围；
3. 适合用来表达什么（如“无语”“震惊”“幸灾乐祸”“摆烂”）。

收藏者备注（仅供参考）：{hint}"""


def _atomic_write(target: str, raw: bytes) -> None:
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    tmp = target + ".tmp"
    with open(tmp, "wb") as f:
        f.write(raw)
    os.replace(tmp, target)


def _unlink(path: Any) -> None:
    if not path:
        return
    with contextlib.suppress(OSError):
        os.remove(str(path))


def _guess_ext(raw: bytes) -> str:
    try:
        import filetype

        guessed = filetype.guess(raw)
        if guessed is not None and guessed.extension:
            return f".{guessed.extension}"
    except Exception:
        pass
    return ".jpg"


def _read_file(path: str) -> bytes:
    with open(path, "rb") as f:
        return f.read()


def _index_text(keywords: str, desc: str, md5: str) -> str:
    """检索文本：关键词在前（BM25 权重更高），md5 短缀保证每条唯一，
    避开 MemoryStore 对相同 text 的去重（不同图片的描述可能一模一样）。"""
    tag = f"[stk:{md5[:8]}]"
    head = " ".join(part for part in (keywords.strip(), desc.strip()) if part)
    budget = INDEX_TEXT_MAX - len(tag) - 1
    if len(head) > budget:
        head = head[:budget]
    return f"{head} {tag}"


class StickerStore(MemoryStore):
    """表情包库：MemoryStore 条目 + 图片文件管理。"""

    def __init__(self, path: str = STICKERS_PATH, limit: int | None = None) -> None:
        if limit is None:
            limit = int(config.others.get("agent_sticker_limit") or 500)
        super().__init__(path, limit=limit)
        self.files_dir = path + ".files"
        os.makedirs(self.files_dir, exist_ok=True)

    # ------------------------------------------------------------------ #
    # 增删查
    # ------------------------------------------------------------------ #

    def add_sticker(self, raw: bytes, desc: str, keywords: str = "", adder: int = 0) -> dict[str, Any]:
        """收藏一张表情包，返回条目（含 id / file / desc / keywords / adder）。

        同一张图（md5 相同）重复收藏时直接返回已存在的条目，不重复生成描述。
        超出 limit 时 MemoryStore 淘汰最旧条目，这里同步回收其图片文件。
        """
        md5 = hashlib.md5(raw).hexdigest()
        for entry in self.entries:
            if entry.get("md5") == md5:
                return entry
        file_path = os.path.join(self.files_dir, f"{md5}{_guess_ext(raw)}")
        _atomic_write(file_path, raw)
        before = len(self.entries)
        oldest = self.entries[0] if before >= self.limit else None
        mem_id = self.add(_index_text(keywords, desc, md5))
        entry = self._entry_by_id(mem_id)
        if entry is None:
            # 理论不可达（text 已按 md5 保证唯一）；不写半截元数据，文件保留可手动清理
            return {}
        entry.update({"file": file_path, "md5": md5, "adder": adder, "keywords": keywords, "desc": desc})
        self._persist()
        if oldest is not None and len(self.entries) <= before:
            _unlink(oldest.get("file"))  # 超量淘汰：回收最旧条目的图片
        return entry

    def delete_sticker(self, sticker_id: int) -> dict[str, Any] | None:
        """删除指定 id 的表情包并移除图片文件；成功返回被删条目，不存在返回 None。"""
        entry = self.get(sticker_id)
        if entry is None:
            return None
        if not self.delete(int(sticker_id)):
            return None
        _unlink(entry.get("file"))
        return entry

    def get(self, sticker_id: int) -> dict[str, Any] | None:
        return self._entry_by_id(int(sticker_id))

    def find_by_md5(self, raw: bytes) -> dict[str, Any] | None:
        """按图片内容查已收藏条目（重复收藏时跳过描述生成）。"""
        md5 = hashlib.md5(raw).hexdigest()
        for entry in self.entries:
            if entry.get("md5") == md5:
                return entry
        return None

    def search(self, query: str, top_k: int = 5) -> list[dict[str, Any]]:
        """混合检索（向量 + 关键词 + 时间加权），返回带 score 的条目列表。"""
        found = self.query_entries(query, max(1, top_k))
        return [{**entry, "score": round(score, 4)} for entry, score in found if entry.get("file")]

    def list_recent(self, limit: int = 10) -> list[dict[str, Any]]:
        """按收藏时间倒序返回最近条目。"""
        return [dict(entry) for entry in reversed(self.entries[-max(1, limit) :])]

    # ------------------------------------------------------------------ #
    # 内部
    # ------------------------------------------------------------------ #

    def _entry_by_id(self, sticker_id: int) -> dict[str, Any] | None:
        for entry in self.entries:
            if int(entry.get("id", -1)) == sticker_id:
                return entry
        return None


async def describe_sticker_image(raw: bytes, hint: str = "") -> str:
    """用 Gemini 视觉生成表情包描述摘要；未配置 gemini_key 或调用失败时返回空串（调用方降级）。"""
    key = config.others.get("gemini_key")
    if not key:
        return ""
    try:
        import filetype
        from google import genai
        from google.genai import types as genai_types

        guessed = filetype.guess(raw)
        mime = guessed.mime if guessed is not None else "image/png"
        model = cast(str, config.others.get("gemini_model") or "gemini-3.5-flash-lite")
        cli = genai.Client(api_key=key)
        prompt = STICKER_DESCRIBE_PROMPT.format(hint=hint.strip() or "（无）")
        res = await asyncio.to_thread(
            cli.models.generate_content,
            model=model,
            contents=cast(
                Any,
                [
                    genai_types.Part.from_bytes(data=raw, mime_type=mime),
                    genai_types.Part.from_text(text=prompt),
                ],
            ),
        )
        return (res.text or "").strip()[:DESC_MAX_CHARS]
    except Exception:
        return ""


_STORE: StickerStore | None = None


def get_sticker_store() -> StickerStore:
    global _STORE
    if _STORE is None:
        _STORE = StickerStore()
    return _STORE


async def download_sticker_image(source: str) -> bytes | None:
    """下载待收藏的图片字节;http(s) 走网络、file:// 读本地,失败返回 None。"""
    try:
        if source.startswith("http"):
            from hyperot.network import httpx_get

            resp = await httpx_get(source)
            if resp.status_code != 200:
                return None
            return resp.content
        if source.startswith("file://"):
            return await asyncio.to_thread(_read_file, source[len("file://") :])
    except Exception:
        return None
    return None


async def collect_sticker(source: str, keywords: str = "", adder: int = 0) -> dict[str, Any]:
    """下载图片并入库:md5 去重 → Gemini 描述 → 写文件与条目。

    命令(.ag.stk.add)与工具(sticker_add)共用;表情包库是全局共享的单例,
    不区分用户,adder 仅作展示元数据。成功返回条目(重复收藏时带 duplicate=True),
    失败返回 {"error": 中文原因}。
    """
    raw = await download_sticker_image(source)
    if not raw:
        return {"error": "图片下载失败,换个图片或稍后再试"}
    store = get_sticker_store()
    existed = store.find_by_md5(raw)
    if existed is not None:
        return {**existed, "duplicate": True}
    desc = await describe_sticker_image(raw, keywords)
    if not desc:
        # Gemini 不可用(未配 key 或调用失败)时退化为用户关键词,保证收藏不失败
        desc = keywords or "(未生成描述)"
    entry = await asyncio.to_thread(store.add_sticker, raw, desc, keywords, adder)
    if not entry:
        return {"error": "收藏失败,请稍后再试"}
    return entry
