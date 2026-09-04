"""Text Store module.

This module belongs to `writing_agent.v2` in the writing-agent codebase.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path


class TextStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _path(self, block_id: str, suffix: str) -> Path:
        if not re.fullmatch(r"[\w-]+", block_id):
            raise ValueError("invalid block id")
        path = self.root / f"{block_id}.{suffix}"
        if path.is_symlink():
            raise ValueError("block file must not be a symlink")
        return path

    def _put(self, value: str, *, block_id: str | None, prefix: str, suffix: str) -> str:
        payload = value.encode("utf-8")
        content_id = f"{prefix}_sha256_{hashlib.sha256(payload).hexdigest()}"
        # Content-addressed IDs are immutable because other documents may reference them.
        bid = block_id or content_id
        if re.fullmatch(r"\w+_sha256_[0-9a-f]{64}", bid):
            bid = content_id
        path = self._path(bid, suffix)
        try:
            if path.read_bytes() == payload:
                return bid
        except FileNotFoundError:
            pass
        self.root.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".block-", suffix=".tmp", dir=self.root)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(payload)
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return bid

    def put_text(self, text: str, *, block_id: str | None = None) -> str:
        return self._put(text or "", block_id=block_id, prefix="p", suffix="txt")

    def get_text(self, block_id: str) -> str:
        path = self._path(block_id, "txt")
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def put_json(self, obj: object, *, block_id: str | None = None, prefix: str = "j") -> str:
        value = json.dumps(obj or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return self._put(value, block_id=block_id, prefix=prefix, suffix="json")

    def get_json(self, block_id: str) -> object:
        path = self._path(block_id, "json")
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
