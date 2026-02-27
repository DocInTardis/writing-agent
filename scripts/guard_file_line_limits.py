"""Guard File Line Limits command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from fnmatch import fnmatch
from pathlib import Path


def _as_posix(path: Path) -> str:
    return path.as_posix()


def load_policy(path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    include = list(raw.get("include") or [])
    exclude = list(raw.get("exclude") or [])
    default_limits = dict(raw.get("default_limits") or {})
    overrides = dict(raw.get("overrides") or {})
    return {
        "include": include,
        "exclude": exclude,
        "default_limits": default_limits,
        "overrides": overrides,
    }


def _matches_any(rel_path: str, patterns: list[str]) -> bool:
    for pat in patterns:
        if fnmatch(rel_path, pat):
            return True
    return False


def collect_target_files(root: Path, include: list[str], exclude: list[str]) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = _as_posix(path.relative_to(root))
        if include and not _matches_any(rel, include):
            continue
        if exclude and _matches_any(rel, exclude):
            continue
        files.append(path)
    files.sort(key=lambda p: _as_posix(p.relative_to(root)))
    return files


def _line_count(path: Path) -> int:
    return len(path.read_text(encoding="utf-8-sig", errors="ignore").splitlines())


def _limit_for(rel: str, policy: dict) -> int:
    overrides = policy.get("overrides") or {}
    if rel in overrides:
        return int(overrides[rel])
    suffix = Path(rel).suffix.lower()
    default_limits = policy.get("default_limits") or {}
    return int(default_limits.get(suffix, 0))


def evaluate(root: Path, policy: dict) -> dict:
    include = list(policy.get("include") or [])
    exclude = list(policy.get("exclude") or [])
    targets = collect_target_files(root, include, exclude)
    violations: list[dict] = []
    checked: list[dict] = []
    for path in targets:
        rel = _as_posix(path.relative_to(root))
        limit = _limit_for(rel, policy)
        if limit <= 0:
            continue
        lines = _line_count(path)
        row = {"path": rel, "lines": lines, "limit": limit}
        checked.append(row)
        if lines > limit:
            violations.append(row)
    return {
        "ok": len(violations) == 0,
        "checked_count": len(checked),
        "violations": violations,
        "checked": checked,
    }


def _default_out_path() -> Path:
    return Path(".data/out") / f"file_line_limits_guard_{int(time.time())}.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Guard file line limits.")
    parser.add_argument("--config", default="security/file_line_limits.json", help="Policy json path.")
    parser.add_argument("--root", default=".", help="Repository root.")
    parser.add_argument("--out", default="", help="Report output path.")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = (root / config_path).resolve()
    if not config_path.exists():
        report = {"ok": False, "error": f"config not found: {config_path.as_posix()}"}
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2

    policy = load_policy(config_path)
    result = evaluate(root, policy)
    report = {
        "ok": bool(result.get("ok")),
        "config": _as_posix(config_path),
        "root": _as_posix(root),
        "checked_count": int(result.get("checked_count", 0)),
        "violation_count": len(result.get("violations") or []),
        "violations": result.get("violations") or [],
    }
    out_path = Path(str(args.out or "")).resolve() if str(args.out or "").strip() else _default_out_path()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
