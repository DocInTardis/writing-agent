"""Feature Flags module.

This module belongs to `writing_agent` in the writing-agent codebase.
"""

from __future__ import annotations

import json
from pathlib import Path


class FeatureFlags:
    def __init__(self, path: str | Path = "security/feature_flags.json") -> None:
        self.path = Path(path)

    def _load(self) -> dict:
        if not self.path.exists():
            return {"flags": {}}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {"flags": {}}
        except Exception:
            return {"flags": {}}

    def enabled(self, name: str, *, tenant_id: str = "") -> bool:
        data = self._load()
        flags = data.get("flags") if isinstance(data.get("flags"), dict) else {}
        row = flags.get(name)
        if isinstance(row, bool):
            return row
        if not isinstance(row, dict):
            return False
        if tenant_id and isinstance(row.get("tenants"), list):
            return tenant_id in [str(x) for x in row.get("tenants")]
        return bool(row.get("enabled", False))

    def rollout_percent(self, name: str, *, tenant_id: str = "") -> int:
        data = self._load()
        flags = data.get("flags") if isinstance(data.get("flags"), dict) else {}
        row = flags.get(name)
        if not isinstance(row, dict):
            return 0
        if tenant_id and isinstance(row.get("tenants"), list):
            tenants = [str(x) for x in row.get("tenants")]
            if tenants and tenant_id not in tenants:
                return 0
        raw = row.get("rollout_percent")
        try:
            value = int(raw)
        except Exception:
            value = 0
        return max(0, min(100, value))
