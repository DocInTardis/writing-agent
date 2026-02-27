"""Model Router module.

This module belongs to `writing_agent.llm` in the writing-agent codebase.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RoutePolicy:
    complexity_threshold: int = 140
    latency_target_ms: int = 6000
    quality_target: str = "balanced"


@dataclass
class CircuitState:
    failures: int = 0
    opened_at: float = 0.0


class ModelRouter:
    """Task-aware model router with fallback chain and basic resilience controls."""

    def __init__(self, *, policy: RoutePolicy | None = None) -> None:
        self.policy = policy or RoutePolicy()
        self._circuit: dict[str, CircuitState] = {}

    def choose_model(self, *, task: str, prompt_len: int, candidates: list[str]) -> str:
        rows = [str(x).strip() for x in candidates if str(x).strip()]
        if not rows:
            return ""
        complexity = self._estimate_complexity(task=task, prompt_len=prompt_len)
        if complexity >= self.policy.complexity_threshold:
            return rows[0]
        return rows[-1]

    def planner_writer_reviewer(self, *, candidates: list[str]) -> dict[str, str]:
        rows = [str(x).strip() for x in candidates if str(x).strip()]
        if not rows:
            return {"planner": "", "writer": "", "reviewer": ""}
        primary = rows[0]
        secondary = rows[1] if len(rows) > 1 else rows[0]
        return {
            "planner": primary,
            "writer": secondary,
            "reviewer": primary,
        }

    def fallback_chain(self, *, preferred: str, candidates: list[str]) -> list[str]:
        rows = [str(x).strip() for x in candidates if str(x).strip()]
        first = str(preferred or "").strip()
        chain: list[str] = []
        if first:
            chain.append(first)
        for row in rows:
            if row not in chain:
                chain.append(row)
        return chain

    def allow_request(self, model: str, *, cooldown_s: float = 30.0, max_failures: int = 3) -> bool:
        state = self._circuit.get(model)
        if state is None:
            return True
        if state.failures < max_failures:
            return True
        return (time.time() - state.opened_at) >= max(1.0, float(cooldown_s))

    def record_success(self, model: str) -> None:
        self._circuit[model] = CircuitState(failures=0, opened_at=0.0)

    def record_failure(self, model: str) -> None:
        cur = self._circuit.get(model) or CircuitState()
        cur.failures += 1
        cur.opened_at = time.time()
        self._circuit[model] = cur

    def _estimate_complexity(self, *, task: str, prompt_len: int) -> int:
        score = int(prompt_len)
        raw = str(task or "").lower()
        for token in ("review", "citation", "long", "analysis", "compare", "multi"):
            if token in raw:
                score += 40
        return score


class SemanticCache:
    """L1(local process) + L2(file-backed) semantic cache scaffold."""

    def __init__(self, *, l2_path: str = ".data/cache/semantic_cache.json") -> None:
        self._l1: dict[str, Any] = {}
        self.l2_path = l2_path

    def get(self, key: str) -> Any:
        if key in self._l1:
            return self._l1[key]
        try:
            import json
            from pathlib import Path

            path = Path(self.l2_path)
            if path.exists():
                raw = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(raw, dict) and key in raw:
                    self._l1[key] = raw[key]
                    return raw[key]
        except Exception:
            pass
        return None

    def set(self, key: str, value: Any) -> None:
        self._l1[key] = value
        try:
            import json
            from pathlib import Path

            path = Path(self.l2_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            existing = {}
            if path.exists():
                raw = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    existing = raw
            existing[key] = value
            path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass
