"""Read uploaded or downloaded documents with local Python parsers."""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import os
import re
from pathlib import Path
from typing import Any, cast
from urllib.parse import unquote, urlparse

from hyperot import common, configurator
from hyperot.network import httpx_get

from modules.AgentRuntime.document_reader import (
    MAX_DOCUMENT_BYTES,
    DocumentReadError,
    parse_document,
    render_pdf_pages,
)
from modules.AgentTools.info_tools import GEMINI_MODEL
from modules.AgentTools.registry import AgentToolBase, ToolContext, tool

config = configurator.BotConfig.get("hyper-bot")

IMAGE_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".tif": "image/tiff",
    ".tiff": "image/tiff",
}


def _extract_data(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {}
    data = result.get("data")
    return data if isinstance(data, dict) else result


async def _custom_result(action: Any, **kwargs: Any) -> dict[str, Any]:
    result = await action(**kwargs)
    if isinstance(result, dict):
        return _extract_data(result)
    if isinstance(result, str):
        response = await common.Ret.fetch(result)
        return _extract_data(response.raw)
    return {}


def _decode_data_uri(value: str) -> bytes | None:
    match = re.fullmatch(r"data:[^;,]+;base64,(.+)", value, flags=re.DOTALL)
    if match is None:
        return None
    return base64.b64decode(match.group(1))


async def _download_url(url: str) -> bytes:
    response = await httpx_get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
    if response.status_code != 200:
        raise DocumentReadError(f"下载失败: HTTP {response.status_code}")
    data = response.content
    if len(data) > MAX_DOCUMENT_BYTES:
        raise DocumentReadError(f"文件超过读取上限 ({MAX_DOCUMENT_BYTES // 1024 // 1024} MB)")
    return data


async def _payload_bytes(payload: dict[str, Any]) -> bytes:
    encoded = payload.get("base64")
    if isinstance(encoded, str) and encoded:
        raw = encoded.removeprefix("base64://")
        try:
            return base64.b64decode(raw, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise DocumentReadError("QQ 文件 base64 内容无效") from exc

    for key in ("url", "file", "path"):
        value = payload.get(key)
        if not isinstance(value, str) or not value:
            continue
        if value.startswith(("http://", "https://")):
            return await _download_url(value)
        data_uri = _decode_data_uri(value)
        if data_uri is not None:
            return data_uri
        path = value[7:] if value.startswith("file://") else value
        if os.path.isfile(path):
            with open(path, "rb") as file:
                data = file.read()
            if len(data) > MAX_DOCUMENT_BYTES:
                raise DocumentReadError(f"文件超过读取上限 ({MAX_DOCUMENT_BYTES // 1024 // 1024} MB)")
            return data
    raise DocumentReadError("QQ 文件没有可用的下载地址或内容")


async def _get_uploaded_payload(
    ctx: ToolContext,
    file_id: str,
    file_name: str,
    group_id: int,
    busid: int,
) -> tuple[dict[str, Any], bytes, str]:
    params: dict[str, Any] = {}
    if file_id:
        params["file_id"] = file_id
    if file_name:
        params["file"] = file_name
    if group_id:
        params["group_id"] = group_id
    if busid:
        params["busid"] = busid
    if not params:
        raise DocumentReadError("必须提供 file_id 或 file_name")

    attempts = [dict(params)]
    if file_id:
        attempts.append({"file_id": file_id})
        if file_name:
            attempts.append({"file": file_name})

    payload: dict[str, Any] = {}
    last_error: Exception | None = None
    for attempt in attempts:
        try:
            payload = await _custom_result(ctx.actions.custom.get_file, **attempt)
            if payload:
                break
        except Exception as exc:
            last_error = exc
    if not payload:
        raise DocumentReadError(f"获取 QQ 文件失败: {last_error!r}")

    data = await _payload_bytes(payload)
    resolved_name = str(payload.get("file_name") or payload.get("name") or file_name or file_id or "uploaded_file")
    return payload, data, resolved_name


def _walk_uploads(value: Any, depth: int = 0) -> list[dict[str, Any]]:
    if depth > 10:
        return []
    if isinstance(value, str):
        text = value.strip()
        if not text.startswith(("{", "[")) or len(text) > 2_000_000:
            return []
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return []
        return _walk_uploads(parsed, depth + 1)
    if isinstance(value, list):
        result: list[dict[str, Any]] = []
        for item in value:
            result.extend(_walk_uploads(item, depth + 1))
        return result
    if not isinstance(value, dict):
        return []

    result: list[dict[str, Any]] = []
    notice_type = value.get("notice_type")
    file_data = value.get("file")
    if notice_type in {"group_upload", "friend_upload"} and isinstance(file_data, dict):
        result.append(
            {
                "file_id": str(file_data.get("id") or file_data.get("file_id") or file_data.get("file") or ""),
                "file_name": str(file_data.get("name") or file_data.get("file_name") or file_data.get("file") or ""),
                "size": file_data.get("size") or file_data.get("file_size") or 0,
                "busid": file_data.get("busid") or 0,
                "group_id": value.get("group_id") or 0,
                "user_id": value.get("user_id") or 0,
                "time": value.get("time") or 0,
                "notice_type": notice_type,
            }
        )
    message = value.get("message")
    if isinstance(message, list):
        for segment in message:
            if not isinstance(segment, dict) or segment.get("type") != "file":
                continue
            segment_data = segment.get("data")
            if not isinstance(segment_data, dict):
                continue
            result.append(
                {
                    "file_id": str(
                        segment_data.get("file_id")
                        or segment_data.get("id")
                        or segment_data.get("file")
                        or ""
                    ),
                    "file_name": str(segment_data.get("file_name") or segment_data.get("name") or ""),
                    "size": segment_data.get("file_size") or segment_data.get("size") or 0,
                    "busid": segment_data.get("busid") or 0,
                    "group_id": value.get("group_id") or 0,
                    "user_id": value.get("user_id") or 0,
                    "time": value.get("time") or 0,
                    "notice_type": "message_file",
                }
            )
    for item in value.values():
        result.extend(_walk_uploads(item, depth + 1))
    return result


def _upload_sort_key(item: dict[str, Any]) -> int:
    return int(item.get("time") or 0)


async def _vision_document(filename: str, images: list[bytes], mime_types: list[str] | None = None) -> str | None:
    key = config.others.get("gemini_key")
    if not key or not images:
        return None
    from google import genai
    from google.genai import types as genai_types

    client = genai.Client(api_key=key)
    parts: list[Any] = [
        genai_types.Part.from_text(
            text=(
                f"请转录文档「{filename}」的全部可见内容。保留标题、段落、表格、公式和关键排版，"
                "按页码顺序输出。只输出文档内容，不要寒暄或解释。"
            )
        )
    ]
    mime_types = mime_types or ["image/png"] * len(images)
    parts.extend(
        genai_types.Part.from_bytes(data=image, mime_type=mime_types[index] if index < len(mime_types) else "image/png")
        for index, image in enumerate(images)
    )
    result = await asyncio.to_thread(
        client.models.generate_content,
        model=GEMINI_MODEL,
        contents=cast(Any, parts),
    )
    return (result.text or "").strip() or None


async def _parse_and_format(data: bytes, filename: str, member: str = "") -> str:
    parsed = await asyncio.to_thread(parse_document, data, filename, member)
    vision_text: str | None = None
    if parsed.kind == "IMAGE":
        import filetype

        guessed = filetype.guess(data)
        mime = guessed.mime if guessed is not None else IMAGE_MIME.get(Path(filename).suffix.lower(), "image/png")
        vision_text = await _vision_document(filename, [data], [mime])
    elif parsed.kind == "PDF" and parsed.metadata.get("scanned"):
        images = await asyncio.to_thread(render_pdf_pages, data)
        vision_text = await _vision_document(filename, images)

    text = vision_text or parsed.text
    header = [
        f"文件: {filename}",
        f"类型: {parsed.kind}",
        f"提取字符: {len(text)}",
    ]
    if parsed.metadata:
        header.append("元数据: " + json.dumps(parsed.metadata, ensure_ascii=False))
    if vision_text:
        header.append("说明: 文本层不足，已使用视觉模型转录" + ("（仅前若干页）" if parsed.kind == "PDF" else ""))
    elif parsed.kind == "PDF" and parsed.metadata.get("scanned"):
        header.append("说明: 看起来是扫描版 PDF，且当前未配置视觉兜底或视觉识别失败")
    if not text and parsed.kind != "ZIP":
        text = "（未提取到可读文本）"
    return "\n".join(header) + "\n---\n" + text


class DocumentTools(AgentToolBase):
    @tool(group="document")
    async def list_uploaded_files(self, ctx: ToolContext, limit: int = 20) -> str:
        """列出当前会话历史中最近上传的 QQ 文件，返回 file_id、文件名、大小和来源。"""
        history = getattr(ctx.runtime, "history", [])
        found: list[dict[str, Any]] = []
        for message in history:
            content = message.get("content") if isinstance(message, dict) else message
            found.extend(_walk_uploads(content))

        unique: dict[tuple[Any, ...], dict[str, Any]] = {}
        for item in found:
            key = (
                item.get("notice_type"),
                item.get("group_id"),
                item.get("user_id"),
                item.get("file_id"),
                item.get("file_name"),
            )
            unique[key] = item
        items = sorted(unique.values(), key=_upload_sort_key, reverse=True)
        limit = max(1, min(limit, 50))
        return json.dumps({"files": items[:limit]}, ensure_ascii=False)

    @tool(group="document", preserve=True)
    async def read_uploaded_file(
        self,
        ctx: ToolContext,
        file_id: str = "",
        file_name: str = "",
        group_id: int = 0,
        busid: int = 0,
        member: str = "",
    ) -> str:
        """读取 QQ 上传文件。

        - file_id / file_name: 来自 group_upload 或 friend_upload 事件，至少提供一个
        - group_id / busid: 部分 OneBot 实现需要，可留空
        - member: ZIP 内文件路径；不填时列出压缩包目录
        """
        try:
            _, data, resolved_name = await _get_uploaded_payload(ctx, file_id, file_name, group_id, busid)
            return await _parse_and_format(data, resolved_name, member)
        except DocumentReadError as exc:
            return f"（QQ 文件读取失败: {exc}）"
        except Exception as exc:
            return f"（QQ 文件解析失败: {exc!r}）"

    @tool(group="document", preserve=True)
    async def read_document(self, ctx: ToolContext, url: str, file_name: str = "", member: str = "") -> str:
        """下载并读取 HTTP(S) 文档，支持 PDF、DOCX、XLSX、PPTX、文本、JSON、CSV、HTML 和 ZIP。

        - url: 文档下载链接
        - file_name: 可选文件名；留空时从 URL 推断
        - member: ZIP 内文件路径；不填时列出压缩包目录
        """
        parsed_url = urlparse(url)
        if parsed_url.scheme not in ("http", "https"):
            return "（文档读取失败: 只允许 HTTP(S) URL；QQ 文件请使用 read_uploaded_file）"
        name = file_name or Path(unquote(parsed_url.path)).name or "document"
        try:
            data = await _download_url(url)
            return await _parse_and_format(data, name, member)
        except DocumentReadError as exc:
            return f"（文档读取失败: {exc}）"
        except Exception as exc:
            return f"（文档解析失败: {exc!r}）"
