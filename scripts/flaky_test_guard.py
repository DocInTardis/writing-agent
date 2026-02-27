"""Flaky Test Guard command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Detect potentially flaky tests from pytest json report")
    parser.add_argument("--report", default=".data/out/pytest_report.json")
    parser.add_argument("--out", default=".data/out/flaky_test_guard.json")
    args = parser.parse_args(argv)

    report = Path(args.report)
    flaky: list[str] = []
    if report.exists():
        try:
            raw = json.loads(report.read_text(encoding="utf-8"))
            tests = raw.get("tests") if isinstance(raw, dict) else []
            if isinstance(tests, list):
                for row in tests:
                    if not isinstance(row, dict):
                        continue
                    nodeid = str(row.get("nodeid") or "")
                    outcome = str(row.get("outcome") or "")
                    longrepr = str(row.get("longrepr") or "")
                    if outcome in {"failed", "error"} and re.search(r"timeout|network|race|flaky", longrepr, re.IGNORECASE):
                        flaky.append(nodeid)
        except Exception:
            pass

    out = {
        "ok": True,
        "flaky_candidates": sorted(set(flaky)),
        "count": len(set(flaky)),
    }
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
