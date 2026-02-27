"""Text Store module.

This module belongs to `writing_agent.v2` in the writing-agent codebase.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path


class TextStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def new_id(self, prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex[:8]}"

    def put_text(self, text: str, *, block_id: str | None = None) -> str:
        bid = block_id or self.new_id("p")
        path = self.root / f"{bid}.txt"
        path.write_text(text or "", encoding="utf-8")
        return bid

    def get_text(self, block_id: str) -> str:
        path = self.root / f"{block_id}.txt"
        if not path.exists():
            return ""
        return path.read_text(encoding="utf-8")

    def put_json(self, obj: object, *, block_id: str | None = None, prefix: str = "j") -> str:
        bid = block_id or self.new_id(prefix)
        path = self.root / f"{bid}.json"
        path.write_text(json.dumps(obj or {}, ensure_ascii=False, indent=2), encoding="utf-8")
        return bid

    def get_json(self, block_id: str) -> object:
        path = self.root / f"{block_id}.json"
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
