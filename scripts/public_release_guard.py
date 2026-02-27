#!/usr/bin/env python3
"""Public Release Guard command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
_VERSION_RE = re.compile(r'__version__\s*=\s*"([^"]+)"')


def _is_semver(value: str) -> bool:
    return bool(_SEMVER_RE.match(str(value or "").strip()))


def _load_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def _extract_version_from_init(path: Path) -> str:
    m = _VERSION_RE.search(_load_text(path))
    return str(m.group(1)).strip() if m else ""


def _load_json_dict(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def _check_row(*, check_id: str, ok: bool, value: Any, expect: str, mode: str = "enforce") -> dict[str, Any]:
    return {
        "id": str(check_id),
        "ok": bool(ok),
        "value": value,
        "expect": str(expect),
        "mode": str(mode or "enforce"),
    }


def _safe_release_notes_path(version: str) -> Path:
    safe = re.sub(r"[^0-9A-Za-z._-]+", "_", str(version or "unknown"))
    return Path(".data/out") / f"release_notes_{safe}.md"


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate public release publishing readiness and notes generation.")
    parser.add_argument("--policy", default="security/public_release_policy.json")
    parser.add_argument("--release-version", default="")
    parser.add_argument("--init-file", default="writing_agent/__init__.py")
    parser.add_argument("--changes-file", default="CHANGES.md")
    parser.add_argument("--write-release-notes", action="store_true")
    parser.add_argument("--release-notes-out", default="")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    started = time.time()
    policy_path = Path(str(args.policy))
    policy = _load_json_dict(policy_path)
    init_path = Path(str(args.init_file))
    changes_path = Path(str(args.changes_file))
    init_version = _extract_version_from_init(init_path)
    release_version = str(args.release_version or os.environ.get("WA_RELEASE_VERSION", "")).strip() or init_version
    release_notes_out = Path(str(args.release_notes_out or _safe_release_notes_path(release_version)))

    checks: list[dict[str, Any]] = []
    checks.append(
        _check_row(
            check_id="policy_loaded",
            ok=bool(policy),
            value=policy_path.as_posix(),
            expect="public release policy should be valid json",
            mode="enforce",
        )
    )
    checks.append(
        _check_row(
            check_id="release_version_semver",
            ok=_is_semver(release_version),
            value=release_version,
            expect="release version should follow semantic version",
            mode="enforce",
        )
    )
    checks.append(
        _check_row(
            check_id="init_version_present",
            ok=_is_semver(init_version),
            value=init_version,
            expect="__version__ should be semantic version",
            mode="enforce",
        )
    )
    checks.append(
        _check_row(
            check_id="init_version_matches_release",
            ok=(not init_version) or init_version == release_version,
            value={"init_version": init_version, "release_version": release_version},
            expect="release version should match package __version__",
            mode="enforce" if bool(args.strict) else "warn",
        )
    )

    checks.append(
        _check_row(
            check_id="changes_file_present",
            ok=changes_path.exists() and changes_path.is_file(),
            value=changes_path.as_posix(),
            expect="changelog source exists",
            mode="enforce",
        )
    )
    checks.append(
        _check_row(
            check_id="changes_file_non_empty",
            ok=len(_load_text(changes_path).strip()) > 0,
            value=changes_path.as_posix(),
            expect="changelog source should not be empty",
            mode="enforce",
        )
    )

    required_docs = [str(x) for x in (policy.get("required_docs") if isinstance(policy.get("required_docs"), list) else [])]
    required_workflows = [str(x) for x in (policy.get("required_workflows") if isinstance(policy.get("required_workflows"), list) else [])]
    required_scripts = [str(x) for x in (policy.get("required_scripts") if isinstance(policy.get("required_scripts"), list) else [])]
    for rel_path in [*required_docs, *required_workflows, *required_scripts]:
        path = Path(rel_path)
        checks.append(
            _check_row(
                check_id=f"path_exists::{rel_path}",
                ok=path.exists(),
                value=rel_path,
                expect="required public release contract path exists",
                mode="enforce",
            )
        )

    notes_required = bool(
        args.write_release_notes
        or bool((policy.get("release_notes") if isinstance(policy.get("release_notes"), dict) else {}).get("required"))
    )
    notes_result: dict[str, Any] = {
        "attempted": False,
        "ok": True,
        "command": [],
        "return_code": 0,
        "stdout_tail": "",
        "stderr_tail": "",
        "out_path": release_notes_out.as_posix(),
    }
    if notes_required:
        cmd = [
            sys.executable,
            "scripts/generate_release_notes.py",
            "--release-version",
            release_version,
            "--changes-file",
            changes_path.as_posix(),
            "--out",
            release_notes_out.as_posix(),
        ]
        run = subprocess.run(cmd, text=True, capture_output=True)
        notes_result = {
            "attempted": True,
            "ok": int(run.returncode) == 0,
            "command": cmd,
            "return_code": int(run.returncode),
            "stdout_tail": str(run.stdout or "")[-1200:],
            "stderr_tail": str(run.stderr or "")[-1200:],
            "out_path": release_notes_out.as_posix(),
        }
    checks.append(
        _check_row(
            check_id="release_notes_generated",
            ok=(not notes_required) or bool(notes_result.get("ok")),
            value=notes_result,
            expect="release notes generation should succeed",
            mode="enforce",
        )
    )
    checks.append(
        _check_row(
            check_id="release_notes_file_exists",
            ok=(not notes_required) or release_notes_out.exists(),
            value=release_notes_out.as_posix(),
            expect="release notes file should exist",
            mode="enforce",
        )
    )
    if notes_required and release_notes_out.exists():
        text = _load_text(release_notes_out)
        checks.append(
            _check_row(
                check_id="release_notes_contains_version",
                ok=release_version in text,
                value={"release_version": release_version, "out_path": release_notes_out.as_posix()},
                expect="release notes should include release version marker",
                mode="enforce",
            )
        )

    enforce_rows = [row for row in checks if str(row.get("mode") or "enforce") == "enforce"]
    ok = all(bool(row.get("ok")) for row in enforce_rows)
    ended = time.time()
    report = {
        "ok": bool(ok),
        "started_at": round(started, 3),
        "ended_at": round(ended, 3),
        "duration_s": round(ended - started, 3),
        "strict": bool(args.strict),
        "policy_file": policy_path.as_posix(),
        "release_version": release_version,
        "init_version": init_version,
        "changes_file": changes_path.as_posix(),
        "release_notes": notes_result,
        "checks": checks,
    }
    out_default = Path(".data/out") / f"public_release_guard_{int(ended)}.json"
    out_path = Path(str(args.out or out_default))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if bool(report.get("ok")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
