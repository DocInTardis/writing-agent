"""Prompt Ab Test command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Simple prompt A/B evaluator scaffold")
    parser.add_argument("--dataset", default="tests/fixtures/content_validation/content_cases_70.json")
    parser.add_argument("--ratio-a", type=float, default=0.5)
    parser.add_argument("--out", default=".data/out/prompt_ab_eval.json")
    args = parser.parse_args(argv)

    ratio = max(0.0, min(1.0, float(args.ratio_a)))
    path = Path(args.dataset)
    rows = []
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                rows = [x for x in raw if isinstance(x, dict)]
        except Exception:
            rows = []

    assign = []
    for idx, row in enumerate(rows):
        seed = abs(hash((idx, row.get("topic") or row.get("prompt") or ""))) % 10000
        arm = "A" if (seed / 10000.0) < ratio else "B"
        assign.append({"idx": idx, "arm": arm, "topic": row.get("topic") or ""})

    report = {
        "ok": True,
        "total": len(assign),
        "arm_a": sum(1 for x in assign if x["arm"] == "A"),
        "arm_b": sum(1 for x in assign if x["arm"] == "B"),
        "assignments": assign[:500],
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
