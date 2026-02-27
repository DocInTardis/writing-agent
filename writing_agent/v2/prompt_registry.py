"""Prompt Registry module.

This module belongs to `writing_agent.v2` in the writing-agent codebase.
"""

from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PromptVariant:
    prompt_id: str
    version: str
    label: str
    cohort: str
    enabled: bool
    rollback_to: str | None
    payload: dict[str, Any]


class PromptRegistry:
    def __init__(self, path: str | Path = ".data/prompt_registry/prompts.json") -> None:
        self.path = Path(path)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema_version": "1.0", "prompts": {}}
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {"schema_version": "1.0", "prompts": {}}

    def save(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        body = dict(payload or {})
        body.setdefault("schema_version", "1.0")
        body.setdefault("updated_at", time.time())
        self.path.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_active(self, prompt_id: str, *, cohort: str = "default") -> PromptVariant | None:
        data = self.load()
        prompts = data.get("prompts") if isinstance(data.get("prompts"), dict) else {}
        variants = prompts.get(prompt_id) if isinstance(prompts.get(prompt_id), list) else []
        rows: list[PromptVariant] = []
        for row in variants:
            if not isinstance(row, dict):
                continue
            rows.append(
                PromptVariant(
                    prompt_id=str(prompt_id),
                    version=str(row.get("version") or ""),
                    label=str(row.get("label") or ""),
                    cohort=str(row.get("cohort") or "default"),
                    enabled=bool(row.get("enabled", True)),
                    rollback_to=str(row.get("rollback_to") or "").strip() or None,
                    payload=dict(row.get("payload") or {}),
                )
            )
        candidates = [r for r in rows if r.enabled and r.cohort in {cohort, "all", "default"}]
        if not candidates:
            return None
        candidates.sort(key=lambda x: x.version, reverse=True)
        return candidates[0]

    def choose_ab(self, prompt_id: str, *, user_key: str, ratio_a: float = 0.5) -> str:
        ratio = max(0.0, min(1.0, float(ratio_a)))
        seed = abs(hash((prompt_id, user_key))) % 10000
        return "A" if (seed / 10000.0) < ratio else "B"

    def rollback(self, prompt_id: str, to_version: str) -> bool:
        data = self.load()
        prompts = data.get("prompts") if isinstance(data.get("prompts"), dict) else {}
        variants = prompts.get(prompt_id)
        if not isinstance(variants, list):
            return False
        changed = False
        for row in variants:
            if not isinstance(row, dict):
                continue
            row["enabled"] = str(row.get("version") or "") == str(to_version)
            row["rollback_to"] = str(to_version)
            changed = True
        if changed:
            self.save(data)
        return changed


def prompt_schema_valid(payload: dict[str, Any]) -> bool:
    required = {"system", "developer", "task", "style", "citation"}
    return required.issubset(set(payload.keys()))


def fallback_prompt_payload() -> dict[str, str]:
    return {
        "system": "You are a writing assistant.",
        "developer": "Follow document structure and safety constraints.",
        "task": "Generate coherent sections with proper headings.",
        "style": "Use formal and concise language.",
        "citation": "Cite only verifiable sources.",
    }
