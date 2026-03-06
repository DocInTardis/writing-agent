"""Prompt registry with versioning, release governance and rollback support."""

from __future__ import annotations

import hashlib
import json
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
    owner: str
    status: str
    tags: tuple[str, ...]
    created_at: float
    updated_at: float
    changelog: str
    rollback_to: str | None
    payload: dict[str, Any]


class PromptRegistry:
    def __init__(self, path: str | Path = ".data/prompt_registry/prompts.json") -> None:
        self.path = Path(path)

    def load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"schema_version": "1.1", "updated_at": time.time(), "prompts": {}, "policy": {}}
        # Accept BOM-prefixed JSON files to avoid hard failures across editors.
        raw = json.loads(self.path.read_text(encoding="utf-8-sig"))
        if not isinstance(raw, dict):
            return {"schema_version": "1.1", "updated_at": time.time(), "prompts": {}, "policy": {}}
        raw.setdefault("schema_version", "1.1")
        raw.setdefault("updated_at", time.time())
        raw.setdefault("prompts", {})
        raw.setdefault("policy", {})
        if not isinstance(raw.get("prompts"), dict):
            raw["prompts"] = {}
        if not isinstance(raw.get("policy"), dict):
            raw["policy"] = {}
        return raw

    def save(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        body = dict(payload or {})
        body.setdefault("schema_version", "1.1")
        body["updated_at"] = time.time()
        body.setdefault("prompts", {})
        body.setdefault("policy", {})
        self.path.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def _variant_from_row(prompt_id: str, row: dict[str, Any]) -> PromptVariant:
        tags_raw = row.get("tags")
        tags: tuple[str, ...]
        if isinstance(tags_raw, list):
            tags = tuple(str(x).strip() for x in tags_raw if str(x).strip())
        else:
            tags = ()
        created_at = float(row.get("created_at") or row.get("createdAt") or 0.0)
        updated_at = float(row.get("updated_at") or row.get("updatedAt") or 0.0)
        if created_at <= 0:
            created_at = updated_at or time.time()
        if updated_at <= 0:
            updated_at = created_at or time.time()
        return PromptVariant(
            prompt_id=str(prompt_id),
            version=str(row.get("version") or ""),
            label=str(row.get("label") or ""),
            cohort=str(row.get("cohort") or "default"),
            enabled=bool(row.get("enabled", True)),
            owner=str(row.get("owner") or "core-team"),
            status=str(row.get("status") or "active"),
            tags=tags,
            created_at=created_at,
            updated_at=updated_at,
            changelog=str(row.get("changelog") or ""),
            rollback_to=str(row.get("rollback_to") or "").strip() or None,
            payload=dict(row.get("payload") or {}),
        )

    @staticmethod
    def _row_from_variant(v: PromptVariant) -> dict[str, Any]:
        return {
            "version": v.version,
            "label": v.label,
            "cohort": v.cohort,
            "enabled": v.enabled,
            "owner": v.owner,
            "status": v.status,
            "tags": list(v.tags),
            "created_at": v.created_at,
            "updated_at": v.updated_at,
            "changelog": v.changelog,
            "rollback_to": v.rollback_to or "",
            "payload": dict(v.payload or {}),
        }

    def list_variants(self, prompt_id: str) -> list[PromptVariant]:
        data = self.load()
        prompts = data.get("prompts") if isinstance(data.get("prompts"), dict) else {}
        rows = prompts.get(prompt_id) if isinstance(prompts.get(prompt_id), list) else []
        variants: list[PromptVariant] = []
        for row in rows:
            if isinstance(row, dict):
                variants.append(self._variant_from_row(prompt_id, row))
        variants.sort(key=lambda x: (x.version, x.updated_at), reverse=True)
        return variants

    def get_variant(self, prompt_id: str, version: str) -> PromptVariant | None:
        wanted = str(version or "").strip()
        if not wanted:
            return None
        for item in self.list_variants(prompt_id):
            if str(item.version) == wanted:
                return item
        return None

    def get_active(self, prompt_id: str, *, cohort: str = "default") -> PromptVariant | None:
        cohort_key = str(cohort or "default").strip() or "default"
        candidates = [
            x
            for x in self.list_variants(prompt_id)
            if x.enabled and x.cohort in {cohort_key, "all", "default"}
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda x: (x.version, x.updated_at), reverse=True)
        return candidates[0]

    def choose_ab(self, prompt_id: str, *, user_key: str, ratio_a: float = 0.5) -> str:
        ratio = max(0.0, min(1.0, float(ratio_a)))
        seed = f"{prompt_id}|{user_key}".encode("utf-8", errors="ignore")
        digest = hashlib.sha256(seed).hexdigest()[:8]
        value = int(digest, 16) / float(0xFFFFFFFF)
        return "A" if value < ratio else "B"

    def register_variant(
        self,
        *,
        prompt_id: str,
        version: str,
        payload: dict[str, Any],
        owner: str = "core-team",
        label: str = "",
        cohort: str = "default",
        status: str = "active",
        tags: list[str] | tuple[str, ...] | None = None,
        changelog: str = "",
        enabled: bool = True,
    ) -> PromptVariant:
        data = self.load()
        prompts = data.get("prompts") if isinstance(data.get("prompts"), dict) else {}
        rows = prompts.get(prompt_id) if isinstance(prompts.get(prompt_id), list) else []
        now = time.time()
        base_tags = tuple(str(x).strip() for x in (tags or []) if str(x).strip())
        variant = PromptVariant(
            prompt_id=str(prompt_id),
            version=str(version),
            label=str(label or version),
            cohort=str(cohort or "default"),
            enabled=bool(enabled),
            owner=str(owner or "core-team"),
            status=str(status or "active"),
            tags=base_tags,
            created_at=now,
            updated_at=now,
            changelog=str(changelog or ""),
            rollback_to=None,
            payload=dict(payload or {}),
        )

        replaced = False
        for idx, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            if str(row.get("version") or "") != variant.version:
                continue
            old = self._variant_from_row(prompt_id, row)
            variant = PromptVariant(
                prompt_id=variant.prompt_id,
                version=variant.version,
                label=variant.label,
                cohort=variant.cohort,
                enabled=variant.enabled,
                owner=variant.owner,
                status=variant.status,
                tags=variant.tags,
                created_at=old.created_at,
                updated_at=now,
                changelog=variant.changelog or old.changelog,
                rollback_to=variant.rollback_to,
                payload=variant.payload,
            )
            rows[idx] = self._row_from_variant(variant)
            replaced = True
            break

        if not replaced:
            rows.append(self._row_from_variant(variant))

        prompts[prompt_id] = rows
        data["prompts"] = prompts
        self.save(data)
        return variant

    def set_active(self, prompt_id: str, version: str, *, cohort: str = "default") -> bool:
        target = str(version or "").strip()
        if not target:
            return False
        data = self.load()
        prompts = data.get("prompts") if isinstance(data.get("prompts"), dict) else {}
        rows = prompts.get(prompt_id)
        if not isinstance(rows, list):
            return False
        changed = False
        for row in rows:
            if not isinstance(row, dict):
                continue
            same_cohort = str(row.get("cohort") or "default") in {cohort, "default", "all"}
            if not same_cohort:
                continue
            row_version = str(row.get("version") or "")
            enabled = row_version == target
            if bool(row.get("enabled", True)) != enabled:
                row["enabled"] = enabled
                row["updated_at"] = time.time()
                changed = True
        if changed:
            prompts[prompt_id] = rows
            data["prompts"] = prompts
            self.save(data)
        return changed

    def rollback(self, prompt_id: str, to_version: str) -> bool:
        target = str(to_version or "").strip()
        if not target:
            return False
        data = self.load()
        prompts = data.get("prompts") if isinstance(data.get("prompts"), dict) else {}
        rows = prompts.get(prompt_id)
        if not isinstance(rows, list):
            return False
        changed = False
        now = time.time()
        for row in rows:
            if not isinstance(row, dict):
                continue
            row_ver = str(row.get("version") or "")
            row["enabled"] = row_ver == target
            row["rollback_to"] = target
            row["updated_at"] = now
            changed = True
        if changed:
            prompts[prompt_id] = rows
            data["prompts"] = prompts
            self.save(data)
        return changed

    def release_policy(self) -> dict[str, Any]:
        data = self.load()
        policy = data.get("policy") if isinstance(data.get("policy"), dict) else {}
        policy.setdefault("ab_ratio_a", 0.5)
        policy.setdefault("failure_rate_threshold", 0.2)
        policy.setdefault("zh_rate_threshold", 0.85)
        policy.setdefault("structure_rate_threshold", 0.85)
        policy.setdefault("citation_rate_threshold", 0.8)
        return policy

    def update_release_policy(self, patch: dict[str, Any]) -> None:
        data = self.load()
        policy = data.get("policy") if isinstance(data.get("policy"), dict) else {}
        for key, value in dict(patch or {}).items():
            policy[str(key)] = value
        data["policy"] = policy
        self.save(data)

    def should_trip_circuit(self, metrics: dict[str, Any]) -> tuple[bool, list[str]]:
        policy = self.release_policy()
        reasons: list[str] = []

        def _as_float(key: str, default: float = 0.0) -> float:
            try:
                return float(metrics.get(key, default))
            except Exception:
                return default

        failure_rate = _as_float("failure_rate", 0.0)
        zh_rate = _as_float("zh_rate", 1.0)
        structure_rate = _as_float("structure_rate", 1.0)
        citation_rate = _as_float("citation_rate", 1.0)

        if failure_rate > float(policy.get("failure_rate_threshold", 0.2)):
            reasons.append("failure_rate")
        if zh_rate < float(policy.get("zh_rate_threshold", 0.85)):
            reasons.append("zh_rate")
        if structure_rate < float(policy.get("structure_rate_threshold", 0.85)):
            reasons.append("structure_rate")
        if citation_rate < float(policy.get("citation_rate_threshold", 0.8)):
            reasons.append("citation_rate")
        return (len(reasons) > 0), reasons


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
