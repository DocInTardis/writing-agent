"""Disaster Recovery Drill command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import argparse
import json
import shutil
import time
from pathlib import Path


def _copy_tree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Simulate multi-region backup + restore drill")
    parser.add_argument("--primary", default=".data")
    parser.add_argument("--region-a", default=".data/dr/region-a")
    parser.add_argument("--region-b", default=".data/dr/region-b")
    parser.add_argument("--out", default=".data/out/disaster_recovery_drill.json")
    args = parser.parse_args(argv)

    primary = Path(args.primary)
    region_a = Path(args.region_a)
    region_b = Path(args.region_b)

    started = time.time()
    checks: list[dict] = []

    if not primary.exists():
        checks.append({"id": "primary_exists", "ok": False, "value": primary.as_posix()})
        report = {"ok": False, "checks": checks, "started_at": started, "ended_at": time.time()}
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    _copy_tree(primary, region_a)
    checks.append({"id": "backup_region_a", "ok": region_a.exists(), "value": region_a.as_posix()})

    _copy_tree(region_a, region_b)
    checks.append({"id": "restore_region_b", "ok": region_b.exists(), "value": region_b.as_posix()})

    report = {
        "ok": all(bool(c.get("ok")) for c in checks),
        "started_at": started,
        "ended_at": time.time(),
        "checks": checks,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
