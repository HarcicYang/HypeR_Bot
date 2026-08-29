"""基于 URL hash 的磁盘图片缓存。

把远程图片下载为本地文件,按 sha256(url) 作为键,避免在内存中持有
base64 data URI。下载结果不区分成功/失败地常驻内存才是泄漏;这里失败
不落盘,下次重试。
"""

import asyncio
import base64
import hashlib
import os

EXT_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}

CACHE_DIR = "./temps/image_cache"


def _path_for(url: str) -> str:
    return os.path.join(CACHE_DIR, hashlib.sha256(url.encode("utf-8")).hexdigest())


def _data_uri(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    mime = EXT_MIME.get(ext, "application/octet-stream")
    with open(path, "rb") as f:
        raw = f.read()
    if not raw or len(raw) > 10 * 1024 * 1024:
        raise ValueError("cached image empty or too large")
    return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"


async def load_or_download(url: str) -> str | None:
    """返回可直接放进 OpenAI image_url 的 data URI;失败返回 None。"""
    path = _path_for(url)
    try:
        return await asyncio.to_thread(_read_existing, path)
    except (OSError, ValueError):
        pass
    try:
        from hyperot.network import httpx_get

        resp = await httpx_get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
        if resp.status_code != 200:
            return None
        raw = resp.content
        if not raw or len(raw) > 10 * 1024 * 1024:
            return None
        import filetype

        guessed = filetype.guess(raw)
        mime = guessed.mime if guessed is not None else "image/png"
        ext = "." + mime.split("/")[-1] if "/" in mime else ".bin"
        target = path + ext
        await asyncio.to_thread(_atomic_write, target, raw)
        return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"
    except Exception:
        return None


def _read_existing(path: str) -> str:
    matches = [
        os.path.join(CACHE_DIR, name)
        for name in os.listdir(CACHE_DIR)
        if os.path.splitext(name)[0] == os.path.basename(path)
    ]
    for m in matches:
        try:
            return _data_uri(m)
        except (OSError, ValueError):
            continue
    raise FileNotFoundError(path)


def _atomic_write(target: str, raw: bytes) -> None:
    os.makedirs(os.path.dirname(target), exist_ok=True)
    tmp = target + ".tmp"
    with open(tmp, "wb") as f:
        f.write(raw)
    os.replace(tmp, target)
