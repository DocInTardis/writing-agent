"""Guard repository hygiene.

Blocks generated output roots and scratch files from leaking into the worktree.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from fnmatch import fnmatch
from pathlib import Path


def _as_posix(path: Path) -> str:
    return path.as_posix()


def _pattern_variants(pattern: str) -> list[str]:
    marker = "**/"
    seen = {str(pattern or "")}
    pending = [str(pattern or "")]
    while pending:
        current = pending.pop()
        idx = current.find(marker)
        while idx >= 0:
            collapsed = current[:idx] + current[idx + len(marker) :]
            if collapsed not in seen:
                seen.add(collapsed)
                pending.append(collapsed)
            idx = current.find(marker, idx + 1)
    return list(seen)


def _matches_any(path: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        for variant in _pattern_variants(pattern):
            if fnmatch(path, variant):
                return pattern
    return None


def load_policy(path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {
        "forbidden_roots": sorted({str(item or "").strip() for item in raw.get("forbidden_roots") or [] if str(item or "").strip()}),
        "forbidden_globs": [str(item or "").strip() for item in raw.get("forbidden_globs") or [] if str(item or "").strip()],
        "allow": [str(item or "").strip() for item in raw.get("allow") or [] if str(item or "").strip()],
    }


def _run_git_paths(root: Path) -> list[str] | None:
    safe_root = root.resolve().as_posix()
    command = [
        "git",
        "-c",
        f"safe.directory={safe_root}",
        "-C",
        str(root.resolve()),
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
        "--full-name",
    ]
    try:
        completed = subprocess.run(command, capture_output=True, text=True, check=True)
    except Exception:
        return None
    rows = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    return sorted(set(rows))


def collect_paths(root: Path) -> list[str]:
    git_rows = _run_git_paths(root)
    if git_rows is not None:
        return git_rows
    rows: list[str] = []
    for path in root.rglob("*"):
        if path.is_file():
            rows.append(_as_posix(path.relative_to(root)))
    return sorted(set(rows))


def evaluate_paths(paths: list[str], policy: dict) -> dict:
    allow = list(policy.get("allow") or [])
    forbidden_roots = set(policy.get("forbidden_roots") or [])
    forbidden_globs = list(policy.get("forbidden_globs") or [])

    violations: list[dict[str, str]] = []
    checked: list[str] = []
    for rel in paths:
        rel_text = str(rel or "").strip().replace("\\", "/")
        if not rel_text:
            continue
        if _matches_any(rel_text, allow):
            continue
        checked.append(rel_text)

        root_name = Path(rel_text).parts[0] if Path(rel_text).parts else ""
        if root_name in forbidden_roots:
            violations.append({"path": rel_text, "kind": "forbidden_root", "rule": root_name})
            continue

        match = _matches_any(rel_text, forbidden_globs)
        if match is None:
            match = _matches_any(Path(rel_text).name, forbidden_globs)
        if match is not None:
            violations.append({"path": rel_text, "kind": "forbidden_glob", "rule": match})

    return {
        "ok": len(violations) == 0,
        "checked_count": len(checked),
        "violation_count": len(violations),
        "violations": violations,
    }


def evaluate(root: Path, policy: dict) -> dict:
    return evaluate_paths(collect_paths(root), policy)


def _default_out_path() -> Path:
    return Path(".data/out") / f"repo_hygiene_guard_{int(time.time())}.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Guard repository hygiene.")
    parser.add_argument("--config", default="security/repo_hygiene_policy.json", help="Policy json path.")
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
        "violation_count": int(result.get("violation_count", 0)),
        "violations": result.get("violations") or [],
    }
    out_path = Path(str(args.out or "")).resolve() if str(args.out or "").strip() else _default_out_path()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
