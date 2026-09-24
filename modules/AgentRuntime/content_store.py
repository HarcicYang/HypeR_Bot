"""Session-scoped storage for complete tool output.

Large tool results are written to disk and represented in model context by a
short preview plus a stable content id. The model can search or page through
the original text with the content tools.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from hyperot import configurator

config = configurator.BotConfig.get("hyper-bot")


def _config_int(name: str, default: int) -> int:
    value = config.others.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


ROOT_DIR = Path("./temps/agent_content")
INLINE_CHARS = max(1, _config_int("agent_content_inline_chars", 4000))
PREVIEW_CHARS = max(1, _config_int("agent_content_preview_chars", 1200))
MAX_READ_CHARS = max(1, _config_int("agent_content_read_chars", 12000))
MAX_ITEM_CHARS = max(0, _config_int("agent_content_max_item_chars", 10_000_000))
TTL_HOURS = _config_int("agent_content_ttl_hours", 168)
MAX_ITEMS_PER_SCOPE = _config_int("agent_content_max_items", 300)
MAX_TOTAL_MB = _config_int("agent_content_max_mb", 512)
CLEANUP_INTERVAL_SECONDS = max(1, _config_int("agent_content_cleanup_interval", 60))
SEARCH_SNIPPET_CHARS = max(100, _config_int("agent_content_search_snippet_chars", 1200))

_STORE_LOCK = threading.RLock()
_last_cleanup = 0.0
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")


def _safe_scope(scope: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", scope or "default").strip("._")
    return (cleaned or "default")[:100]


def _atomic_write(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{uuid.uuid4().hex}.tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(data)
        os.replace(tmp, path)
    finally:
        with contextlib.suppress(OSError):
            os.remove(tmp)


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    _atomic_write(path, json.dumps(data, ensure_ascii=False, indent=2))


def _query_terms(query: str) -> list[str]:
    query = query.strip().lower()
    if not query:
        return []
    terms = {query}
    terms.update(re.findall(r"[a-z0-9_./:+-]{2,}", query))
    for chunk in re.findall(r"[\u4e00-\u9fff]+", query):
        if len(chunk) <= 8:
            terms.add(chunk)
        for size in (2, 3):
            terms.update(chunk[index : index + size] for index in range(max(0, len(chunk) - size + 1)))
    return sorted((term for term in terms if len(term) >= 2), key=len, reverse=True)[:64]


def _accessed_at(meta: dict[str, Any]) -> float:
    return float(meta.get("accessed_at") or meta.get("created_at") or 0)


def _line_match_score(item: tuple[int, int]) -> int:
    return item[1]


def _range_sort_score(item: list[int]) -> int:
    return item[3]


def _entry_accessed(item: tuple[Path, Path, dict[str, Any]]) -> float:
    return _accessed_at(item[2])


class ContentStore:
    """Store and retrieve complete text for one Agent context."""

    def __init__(self, scope: str) -> None:
        self.scope = _safe_scope(scope)
        self.directory = ROOT_DIR / self.scope

    @staticmethod
    def should_preserve(text: str) -> bool:
        return len(text) > INLINE_CHARS

    @staticmethod
    def preview(text: str) -> str:
        if len(text) <= PREVIEW_CHARS:
            return text
        return text[:PREVIEW_CHARS] + "\n..."

    def _paths(self, content_id: str) -> tuple[Path, Path]:
        if not _ID_RE.fullmatch(content_id):
            raise ValueError("content_id 格式非法")
        return self.directory / f"{content_id}.txt", self.directory / f"{content_id}.json"

    def put(
        self,
        text: str,
        *,
        kind: str,
        source: str = "",
        title: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Persist text and return its metadata."""
        now = int(time.time())
        content_id = f"c_{now}_{uuid.uuid4().hex[:10]}"
        original_chars = len(text)
        stored = text[:MAX_ITEM_CHARS] if MAX_ITEM_CHARS > 0 else text
        text_path, meta_path = self._paths(content_id)
        meta: dict[str, Any] = {
            "content_id": content_id,
            "scope": self.scope,
            "kind": kind or "content",
            "source": source or "",
            "title": title or "",
            "chars": len(stored),
            "original_chars": original_chars,
            "truncated": len(stored) < original_chars,
            "created_at": now,
            "accessed_at": now,
        }
        if metadata:
            meta["metadata"] = metadata
        with _STORE_LOCK:
            self.directory.mkdir(parents=True, exist_ok=True)
            _atomic_write(text_path, stored)
            _atomic_write_json(meta_path, meta)
            self._maybe_cleanup_locked()
        return meta

    def info(self, content_id: str) -> dict[str, Any] | None:
        try:
            text_path, meta_path = self._paths(content_id)
        except ValueError:
            return None
        with _STORE_LOCK:
            if not text_path.is_file():
                with contextlib.suppress(OSError):
                    meta_path.unlink()
                return None
            meta = self._load_meta(meta_path)
            if meta is None:
                return None
            self._touch(meta, meta_path)
            return meta

    def list(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return recently used content metadata for this scope."""
        limit = max(1, min(limit, 100))
        if not self.directory.is_dir():
            return []
        entries: list[dict[str, Any]] = []
        with _STORE_LOCK:
            for meta_path in self.directory.glob("*.json"):
                meta = self._load_meta(meta_path)
                if meta is not None:
                    entries.append(meta)
        entries.sort(
            key=_accessed_at,
            reverse=True,
        )
        keys = (
            "content_id",
            "kind",
            "source",
            "title",
            "chars",
            "original_chars",
            "truncated",
            "created_at",
            "accessed_at",
        )
        return [{key: item.get(key) for key in keys} for item in entries[:limit]]

    def read(self, content_id: str, offset: int = 0, limit: int = 4000) -> dict[str, Any]:
        """Read a character range and return the continuation cursor."""
        with _STORE_LOCK:
            info = self.info(content_id)
            if info is None:
                return {"error": f"内容 {content_id} 不存在或已清理"}
            text_path, _ = self._paths(content_id)
            try:
                text = text_path.read_text(encoding="utf-8")
            except OSError:
                return {"error": f"内容 {content_id} 读取失败"}

        total = len(text)
        if offset < 0:
            offset = max(0, total + offset)
        offset = min(max(0, offset), total)
        limit = max(1, min(limit, MAX_READ_CHARS))
        end = min(total, offset + limit)
        chunk = text[offset:end]
        return {
            "content_id": content_id,
            "offset": offset,
            "end": end,
            "total_chars": total,
            "next_offset": end if end < total else None,
            "item_truncated": bool(info.get("truncated")),
            "text": chunk,
        }

    def search(
        self,
        content_id: str,
        query: str,
        max_results: int = 5,
        context_lines: int = 2,
    ) -> dict[str, Any]:
        """Search lines and return merged snippets with exact character ranges."""
        terms = _query_terms(query)
        if not terms:
            return {"error": "搜索关键词不能为空"}
        with _STORE_LOCK:
            info = self.info(content_id)
            if info is None:
                return {"error": f"内容 {content_id} 不存在或已清理"}
            text_path, _ = self._paths(content_id)
            try:
                text = text_path.read_text(encoding="utf-8")
            except OSError:
                return {"error": f"内容 {content_id} 读取失败"}

        lines = text.splitlines(keepends=True)
        if not lines and text:
            lines = [text]
        offsets: list[int] = []
        cursor = 0
        for line in lines:
            offsets.append(cursor)
            cursor += len(line)

        scored: list[tuple[int, int]] = []
        query_lower = query.strip().lower()
        for index, line in enumerate(lines):
            lower = line.lower()
            score = 5 if query_lower in lower else 0
            score += sum(lower.count(term) for term in terms)
            if score:
                scored.append((score, index))
        if not scored:
            return {"content_id": content_id, "query": query, "matches": []}

        context_lines = max(0, min(context_lines, 10))
        max_results = max(1, min(max_results, 20))
        ranges: list[list[int]] = []
        for score, line_index in sorted(scored, key=_line_match_score):
            start = max(0, line_index - context_lines)
            end = min(len(lines) - 1, line_index + context_lines)
            if ranges and start <= ranges[-1][1] + 1:
                ranges[-1][1] = max(ranges[-1][1], end)
                ranges[-1][2] += 1
                ranges[-1][3] = max(ranges[-1][3], score)
            else:
                ranges.append([start, end, 1, score])

        ranges.sort(key=_range_sort_score, reverse=True)
        matches: list[dict[str, Any]] = []
        for start, end, hit_count, _ in ranges[:max_results]:
            snippet = "".join(lines[start : end + 1])
            if len(snippet) > SEARCH_SNIPPET_CHARS:
                snippet = snippet[:SEARCH_SNIPPET_CHARS] + "\n..."
            start_offset = offsets[start]
            end_offset = offsets[end + 1] if end + 1 < len(offsets) else len(text)
            matches.append(
                {
                    "start_offset": start_offset,
                    "end_offset": end_offset,
                    "start_line": start + 1,
                    "end_line": end + 1,
                    "hit_lines": hit_count,
                    "text": snippet,
                }
            )
        return {
            "content_id": content_id,
            "query": query,
            "total_chars": len(text),
            "matches": matches,
        }

    def _load_meta(self, path: Path) -> dict[str, Any] | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return data if isinstance(data, dict) else None

    def _touch(self, meta: dict[str, Any], path: Path) -> None:
        now = int(time.time())
        if now - int(meta.get("accessed_at") or 0) < 300:
            return
        meta["accessed_at"] = now
        with contextlib.suppress(OSError):
            _atomic_write_json(path, meta)

    def _maybe_cleanup_locked(self) -> None:
        global _last_cleanup
        now = time.time()
        scope_count = len(list(self.directory.glob("*.json"))) if self.directory.is_dir() else 0
        scope_overflow = MAX_ITEMS_PER_SCOPE > 0 and scope_count > MAX_ITEMS_PER_SCOPE
        if not scope_overflow and now - _last_cleanup < CLEANUP_INTERVAL_SECONDS:
            return
        try:
            with contextlib.suppress(Exception):
                cleanup_all_locked(now)
        finally:
            _last_cleanup = now


def _iter_entries() -> list[tuple[Path, Path, dict[str, Any]]]:
    entries: list[tuple[Path, Path, dict[str, Any]]] = []
    if not ROOT_DIR.is_dir():
        return entries
    for meta_path in ROOT_DIR.glob("*/*.json"):
        text_path = meta_path.with_suffix(".txt")
        if not text_path.is_file():
            with contextlib.suppress(OSError):
                meta_path.unlink()
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            with contextlib.suppress(OSError):
                meta_path.unlink()
            with contextlib.suppress(OSError):
                text_path.unlink()
            continue
        if isinstance(meta, dict):
            entries.append((text_path, meta_path, meta))
    return entries


def _delete_entry(text_path: Path, meta_path: Path) -> None:
    with contextlib.suppress(OSError):
        text_path.unlink()
    with contextlib.suppress(OSError):
        meta_path.unlink()


def cleanup_all_locked(now: float | None = None) -> dict[str, int]:
    """Delete expired, excess, oversized and orphaned content files."""
    now = now or time.time()
    entries = _iter_entries()
    removed = {"expired": 0, "overflow": 0, "orphan": 0}

    if TTL_HOURS > 0:
        cutoff = now - TTL_HOURS * 3600
        for text_path, meta_path, meta in entries:
            accessed = float(meta.get("accessed_at") or meta.get("created_at") or 0)
            if accessed < cutoff:
                _delete_entry(text_path, meta_path)
                removed["expired"] += 1
        entries = _iter_entries()

    if MAX_ITEMS_PER_SCOPE > 0:
        by_scope: dict[str, list[tuple[Path, Path, dict[str, Any]]]] = {}
        for entry in entries:
            by_scope.setdefault(str(entry[2].get("scope") or entry[0].parent.name), []).append(entry)
        for scoped in by_scope.values():
            scoped.sort(key=_entry_accessed)
            for text_path, meta_path, _ in scoped[: max(0, len(scoped) - MAX_ITEMS_PER_SCOPE)]:
                _delete_entry(text_path, meta_path)
                removed["overflow"] += 1
        entries = _iter_entries()

    if MAX_TOTAL_MB > 0:
        total_bytes = 0
        sized: list[tuple[float, int, Path, Path]] = []
        for text_path, meta_path, meta in entries:
            try:
                size = text_path.stat().st_size
            except OSError:
                continue
            total_bytes += size
            accessed = float(meta.get("accessed_at") or meta.get("created_at") or 0)
            sized.append((accessed, size, text_path, meta_path))
        max_bytes = MAX_TOTAL_MB * 1024 * 1024
        for _, size, text_path, meta_path in sorted(sized):
            if total_bytes <= max_bytes:
                break
            _delete_entry(text_path, meta_path)
            total_bytes -= size
            removed["overflow"] += 1

    if ROOT_DIR.is_dir():
        for path in ROOT_DIR.glob("*/*.tmp"):
            with contextlib.suppress(OSError):
                path.unlink()
                removed["orphan"] += 1
        for text_path in ROOT_DIR.glob("*/*.txt"):
            meta_path = text_path.with_suffix(".json")
            if not meta_path.exists():
                with contextlib.suppress(OSError):
                    text_path.unlink()
                    removed["orphan"] += 1
        for scope_dir in ROOT_DIR.iterdir():
            if scope_dir.is_dir() and not any(scope_dir.iterdir()):
                with contextlib.suppress(OSError):
                    scope_dir.rmdir()
    return removed


def cleanup_all() -> dict[str, int]:
    """Thread-safe cleanup entry point for startup and periodic maintenance."""
    global _last_cleanup
    with _STORE_LOCK:
        result = cleanup_all_locked()
        _last_cleanup = time.time()
        return result
