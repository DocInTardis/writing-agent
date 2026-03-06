"""Offline prompt evaluation gate.

Evaluates route prompt candidates against offline quality metrics:
- structure correctness rate
- Chinese ratio (zh_rate)
- hierarchy correctness rate
- citation compliance rate

Input format (JSONL, one case per line), minimum supported fields:
{
  "case_id": "c1",
  "structure_ok": true,
  "zh_rate": 0.97,
  "hierarchy_ok": true,
  "citation_ok": true
}
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from writing_agent.v2.prompt_registry import PromptRegistry


@dataclass
class EvalSummary:
    total: int
    structure_rate: float
    zh_rate: float
    hierarchy_rate: float
    citation_rate: float
    pass_gate: bool
    fail_reasons: list[str]


def _as_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    raw = str(value or "").strip().lower()
    return raw in {"1", "true", "yes", "on", "ok", "pass", "passed"}


def _as_float(value: object, default: float = 0.0) -> float:
    try:
        parsed = float(value)
    except Exception:
        return default
    if parsed != parsed:
        return default
    return parsed


def _load_rows(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            item = json.loads(text)
        except Exception:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def evaluate(rows: list[dict[str, Any]], *, registry: PromptRegistry) -> EvalSummary:
    total = len(rows)
    if total <= 0:
        return EvalSummary(
            total=0,
            structure_rate=0.0,
            zh_rate=0.0,
            hierarchy_rate=0.0,
            citation_rate=0.0,
            pass_gate=False,
            fail_reasons=["empty_dataset"],
        )

    structure_hits = 0
    zh_sum = 0.0
    hierarchy_hits = 0
    citation_hits = 0
    for row in rows:
        if _as_bool(row.get("structure_ok")):
            structure_hits += 1
        zh_sum += max(0.0, min(1.0, _as_float(row.get("zh_rate"), default=0.0)))
        if _as_bool(row.get("hierarchy_ok")):
            hierarchy_hits += 1
        if _as_bool(row.get("citation_ok")):
            citation_hits += 1

    structure_rate = structure_hits / float(total)
    zh_rate = zh_sum / float(total)
    hierarchy_rate = hierarchy_hits / float(total)
    citation_rate = citation_hits / float(total)

    policy = registry.release_policy()
    structure_thr = float(policy.get("structure_rate_threshold", 0.85))
    zh_thr = float(policy.get("zh_rate_threshold", 0.85))
    citation_thr = float(policy.get("citation_rate_threshold", 0.8))

    fail_reasons: list[str] = []
    if structure_rate < structure_thr:
        fail_reasons.append("structure_rate")
    if zh_rate < zh_thr:
        fail_reasons.append("zh_rate")
    # hierarchy is part of structure gate, keep explicit signal for diagnostics.
    if hierarchy_rate < structure_thr:
        fail_reasons.append("hierarchy_rate")
    if citation_rate < citation_thr:
        fail_reasons.append("citation_rate")

    return EvalSummary(
        total=total,
        structure_rate=round(structure_rate, 4),
        zh_rate=round(zh_rate, 4),
        hierarchy_rate=round(hierarchy_rate, 4),
        citation_rate=round(citation_rate, 4),
        pass_gate=len(fail_reasons) == 0,
        fail_reasons=fail_reasons,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Offline prompt quality gate evaluator")
    parser.add_argument("--input", default="deliverables/prompt_offline_eval_cases.jsonl")
    parser.add_argument("--registry", default=".data/prompt_registry/prompts.json")
    parser.add_argument("--out", default=".data/out/prompt_offline_eval_gate.json")
    args = parser.parse_args(argv)

    rows = _load_rows(Path(args.input))
    registry = PromptRegistry(path=args.registry)
    summary = evaluate(rows, registry=registry)

    out = {
        "ok": bool(summary.pass_gate),
        "summary": asdict(summary),
        "input": str(Path(args.input)),
        "registry": str(Path(args.registry)),
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if summary.pass_gate else 2


if __name__ == "__main__":
    raise SystemExit(main())
