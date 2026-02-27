"""Golden Export Regression command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


TARGETS = [
    "tests/fixtures/golden/report.md",
]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Golden export regression checker")
    parser.add_argument("--out", default=".data/out/golden_export_regression.json")
    args = parser.parse_args(argv)

    rows = []
    ok = True
    for target in TARGETS:
        path = Path(target)
        exists = path.exists()
        digest = _sha256(path) if exists else ""
        rows.append({"path": target, "exists": exists, "sha256": digest})
        ok = ok and exists

    report = {"ok": ok, "targets": rows}
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
