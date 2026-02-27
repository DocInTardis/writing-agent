#!/usr/bin/env python3
"""Sensitive Output Scan command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import time
from pathlib import Path
from typing import Any


_DEFAULT_GLOBS = [
    ".data/out/**/*.json",
    ".data/out/**/*.md",
    ".data/out/**/*.log",
    ".data/citation_verify_alert_events.json",
]

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private_key_marker", re.compile(r"-----BEGIN (?:RSA|EC|DSA|OPENSSH|PGP) PRIVATE KEY-----")),
    (
        "credential_assignment",
        re.compile(r"(?i)\b(api[_-]?key|token|secret|password)\b\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{8,}"),
    ),
    ("bearer_token", re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{20,}\b")),
]


def _mask(value: str) -> str:
    text = str(value or "")
    if len(text) <= 4:
        return "***"
    if len(text) <= 8:
        return text[:1] + "***" + text[-1:]
    return text[:3] + "***" + text[-2:]


def _scan_text(text: str, *, path: Path, max_findings: int) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    if max_findings <= 0:
        max_findings = 1_000_000
    for line_no, raw_line in enumerate(str(text or "").splitlines(), start=1):
        line = str(raw_line or "")
        for rule_id, pattern in _PATTERNS:
            for match in pattern.finditer(line):
                secret = str(match.group(0) or "")
                findings.append(
                    {
                        "path": path.as_posix(),
                        "line": line_no,
                        "rule_id": rule_id,
                        "masked_match": _mask(secret),
                    }
                )
                if len(findings) >= max_findings:
                    return findings
    return findings


def _collect_files(globs: list[str]) -> list[Path]:
    out: list[Path] = []
    seen: set[str] = set()
    for raw in globs:
        pattern = str(raw or "").strip()
        if not pattern:
            continue
        for candidate in sorted(glob.glob(pattern, recursive=True)):
            path = Path(candidate)
            if not path.exists() or not path.is_file():
                continue
            key = path.resolve().as_posix().lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(path)
    return out


def _ok(*, check_id: str, ok: bool, value: Any, expect: str, mode: str = "enforce") -> dict[str, Any]:
    return {
        "id": str(check_id),
        "ok": bool(ok),
        "value": value,
        "expect": str(expect),
        "mode": str(mode or "enforce"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan output artifacts for accidentally leaked secrets/tokens.")
    parser.add_argument("--path-glob", action="append", default=[])
    parser.add_argument("--max-findings", type=int, default=0, help="Maximum allowed findings before fail.")
    parser.add_argument("--strict", action="store_true", help="Fail when no files are scanned.")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    started = time.time()
    patterns = [str(x) for x in args.path_glob if str(x).strip()]
    globs = patterns if patterns else list(_DEFAULT_GLOBS)
    files = _collect_files(globs)
    findings: list[dict[str, Any]] = []
    max_capture = max(1, int(args.max_findings) + 50)

    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        matches = _scan_text(text, path=path, max_findings=max_capture - len(findings))
        findings.extend(matches)
        if len(findings) >= max_capture:
            break

    checks = [
        _ok(
            check_id="artifact_files_scanned",
            ok=len(files) > 0,
            value=len(files),
            expect=">0 files scanned",
            mode="enforce" if bool(args.strict) else "warn",
        ),
        _ok(
            check_id="sensitive_findings_threshold",
            ok=len(findings) <= max(0, int(args.max_findings)),
            value=len(findings),
            expect=f"<={max(0, int(args.max_findings))}",
            mode="enforce",
        ),
    ]

    ended = time.time()
    enforce_rows = [row for row in checks if str(row.get("mode") or "enforce") == "enforce"]
    report = {
        "ok": all(bool(row.get("ok")) for row in enforce_rows),
        "started_at": round(started, 3),
        "ended_at": round(ended, 3),
        "duration_s": round(ended - started, 3),
        "strict": bool(args.strict),
        "globs": globs,
        "files_scanned": [path.as_posix() for path in files[:200]],
        "checks": checks,
        "findings": findings[:200],
    }

    out_default = Path(".data/out") / f"sensitive_output_scan_{int(ended)}.json"
    out_path = Path(str(args.out or out_default))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if bool(report.get("ok")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
