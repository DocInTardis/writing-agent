"""Bounded, disposable local cache for generated text.

The byte limit covers indexed text payloads, not user documents or unrelated
files. Instances sharing a directory coordinate within this process.
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from weakref import WeakValueDictionary

logger = logging.getLogger(__name__)


@dataclass
class _CacheState:
    index: dict[str, dict] = field(default_factory=dict)
    lock: Any = field(default_factory=threading.RLock)
    loaded: bool = False


_states: WeakValueDictionary[str, _CacheState] = WeakValueDictionary()
_states_lock = threading.Lock()


class LocalCache:
    """JSON-indexed text cache with entry, payload-byte and age limits."""

    def __init__(
        self,
        cache_dir: Path,
        max_size: int = 500,
        ttl_seconds: float = 86400 * 7,
        *,
        max_bytes: int = 64 * 1024 * 1024,
    ):
        self.cache_dir = Path(cache_dir).resolve()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_size = max(0, int(max_size))
        self.max_bytes = max(0, int(max_bytes))
        self.ttl_seconds = max(0.0, float(ttl_seconds))
        self.index_path = self.cache_dir / "index.json"
        with _states_lock:
            state = _states.get(str(self.cache_dir))
            if state is None:
                state = _CacheState()
                _states[str(self.cache_dir)] = state
            self._state = state
        self._lock = state.lock
        self.index = state.index
        with self._lock:
            if not state.loaded:
                self._load_index()
                state.loaded = True
            self._prune()
            self._save_index()

    def _cache_path(self, key: str) -> Path:
        # Never allow cache metadata to name files outside its own directory.
        if not isinstance(key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", key):
            raise ValueError("invalid cache key")
        path = self.cache_dir / f"{key}.txt"
        if path.is_symlink() or path.resolve().parent != self.cache_dir:
            raise ValueError("cache file must be local")
        return path

    def _load_index(self) -> None:
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(data, dict):
            return
        for key, entry in data.items():
            try:
                self._cache_path(key)
                if not isinstance(entry, dict):
                    continue
                created_at = float(entry.get("created_at", 0))
                last_hit = float(entry.get("last_hit", created_at))
                if not math.isfinite(created_at) or not math.isfinite(last_hit):
                    continue
                self.index[key] = {
                    "created_at": created_at,
                    "last_hit": last_hit,
                    "hits": max(0, int(entry.get("hits", 0))),
                    "metadata": entry.get("metadata", {}),
                }
            except (ValueError, TypeError, OSError, OverflowError):
                continue

    def _save_index(self) -> None:
        temporary = self.index_path.with_suffix(".json.tmp")
        try:
            temporary.write_text(
                json.dumps(self.index, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            temporary.replace(self.index_path)
        except (OSError, TypeError, ValueError):
            logger.debug("Cannot persist disposable cache index", exc_info=True)

    def _make_key(self, *args: str) -> str:
        combined = "|".join(str(a) for a in args if a)
        return hashlib.md5(combined.encode("utf-8")).hexdigest()

    def _remove(self, key: str) -> bool:
        try:
            self._cache_path(key).unlink(missing_ok=True)
        except (OSError, ValueError):
            # Keep it accounted for if the file is locked; don't pretend it freed space.
            return False
        self.index.pop(key, None)
        return True

    def _prune(self, *, incoming_bytes: int = 0, incoming_entries: int = 0, replacing: str | None = None) -> bool:
        now = time.time()
        for key, entry in list(self.index.items()):
            if now - entry["created_at"] > self.ttl_seconds:
                self._remove(key)
        sizes = {}
        for key in list(self.index):
            try:
                sizes[key] = self._cache_path(key).stat().st_size
            except FileNotFoundError:
                self.index.pop(key, None)
            except (OSError, ValueError):
                return False
        used = sum(size for key, size in sizes.items() if key != replacing)
        count = len(sizes) - int(replacing in sizes)
        # True LRU: recent use, not lifetime hit count.
        for key in sorted(sizes, key=lambda k: self.index[k]["last_hit"]):
            if count + incoming_entries <= self.max_size and used + incoming_bytes <= self.max_bytes:
                break
            if key != replacing and self._remove(key):
                used -= sizes[key]
                count -= 1
        return count + incoming_entries <= self.max_size and used + incoming_bytes <= self.max_bytes

    def get(self, key: str) -> str | None:
        path = self._cache_path(key)
        with self._lock:
            entry = self.index.get(key)
            if not entry:
                return None
            if time.time() - entry["created_at"] > self.ttl_seconds:
                self._remove(key)
                self._save_index()
                return None
            try:
                value = path.read_text(encoding="utf-8")
            except FileNotFoundError:
                self.index.pop(key, None)
                self._save_index()
                return None
            except (OSError, UnicodeError):
                return None
            entry["hits"] += 1
            entry["last_hit"] = time.time()
            return value

    def put(self, key: str, value: str, metadata: dict[str, Any] | None = None) -> None:
        path = self._cache_path(key)
        payload = value.encode("utf-8")
        with self._lock:
            if self.max_size == 0 or len(payload) > self.max_bytes:
                # Do not leave a stale value behind when an update is not cacheable.
                self._remove(key)
                self._save_index()
                return
            if not self._prune(incoming_bytes=len(payload), incoming_entries=1, replacing=key):
                self._save_index()
                return
            try:
                path.write_bytes(payload)
            except OSError:
                self._save_index()
                return
            now = time.time()
            self.index[key] = {
                "created_at": now,
                "hits": 0,
                "last_hit": now,
                "metadata": metadata or {},
            }
            self._save_index()

    def get_section(self, section_title: str, instruction: str, min_chars: int) -> str | None:
        return self.get(self._make_key("section", section_title, instruction, str(min_chars)))

    def put_section(self, section_title: str, instruction: str, min_chars: int, content: str) -> None:
        key = self._make_key("section", section_title, instruction, str(min_chars))
        self.put(key, content, metadata={"type": "section", "title": section_title})

    def clear_expired(self) -> int:
        with self._lock:
            now = time.time()
            removed = sum(
                self._remove(key)
                for key, entry in list(self.index.items())
                if now - entry["created_at"] > self.ttl_seconds
            )
            if removed:
                self._save_index()
            return removed

    def stats(self) -> dict:
        with self._lock:
            total_bytes = 0
            for key in self.index:
                try:
                    total_bytes += self._cache_path(key).stat().st_size
                except (OSError, ValueError):
                    pass
            total_hits = sum(e["hits"] for e in self.index.values())
            return {
                "total_entries": len(self.index),
                "total_hits": total_hits,
                "avg_hits": total_hits / max(1, len(self.index)),
                "cache_dir": str(self.cache_dir),
                "total_bytes": total_bytes,
                "max_bytes": self.max_bytes,
            }
