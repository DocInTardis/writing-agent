"""Env Consistency Guard command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except Exception:
        return {}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check dev/staging/prod config consistency")
    parser.add_argument("--dev", default="security/env/dev.json")
    parser.add_argument("--staging", default="security/env/staging.json")
    parser.add_argument("--prod", default="security/env/prod.json")
    parser.add_argument("--out", default=".data/out/env_consistency_guard.json")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)

    dev = _load(Path(args.dev))
    stg = _load(Path(args.staging))
    prod = _load(Path(args.prod))

    keys = sorted(set(dev.keys()) | set(stg.keys()) | set(prod.keys()))
    diffs = []
    for k in keys:
        values = {"dev": dev.get(k), "staging": stg.get(k), "prod": prod.get(k)}
        if values["dev"] != values["staging"] or values["staging"] != values["prod"]:
            diffs.append({"key": k, "values": values})

    report = {
        "ok": len(diffs) == 0,
        "diff_count": len(diffs),
        "diffs": diffs,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.strict and diffs:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
