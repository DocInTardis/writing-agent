#!/usr/bin/env python3
"""Doc Encoding Guard command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from typing import Any

MOJIBAKE_HINTS = (
    "锟",
    "鈥",
    "锛",
    "銆",
    "鏄",
    "鍙",
    "鍚",
    "鍦",
    "鍐",
    "鍑",
    "鎴",
    "闂",
    "瑙",
    "鏃",
    "绗",
    "澶",
)


def _check_row(*, check_id: str, ok: bool, value: Any, expect: str, mode: str = "warn") -> dict[str, Any]:
    return {
        "id": str(check_id),
        "ok": bool(ok),
        "value": value,
        "expect": str(expect),
        "mode": str(mode or "warn"),
    }


def _iter_markdown_files(root: Path) -> list[Path]:
    if not root.exists():
        return []
    return sorted([p for p in root.rglob("*.md") if p.is_file()])


def _mojibake_score(text: str) -> dict[str, Any]:
    hint_count = sum(int(text.count(token)) for token in MOJIBAKE_HINTS)
    non_ws = sum(1 for ch in text if not ch.isspace())
    ratio = float(hint_count) / float(max(1, non_ws))
    return {
        "hint_count": int(hint_count),
        "non_whitespace_chars": int(non_ws),
        "ratio": round(ratio, 8),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate docs markdown encoding quality and mojibake risk.")
    parser.add_argument("--docs-root", default="docs")
    parser.add_argument("--max-suspicious-files", type=int, default=0)
    parser.add_argument("--min-hint-count", type=int, default=8)
    parser.add_argument("--min-hint-ratio", type=float, default=0.03)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    started = time.time()
    mode = "enforce" if bool(args.strict) else "warn"
    checks: list[dict[str, Any]] = []

    root = Path(str(args.docs_root))
    files = _iter_markdown_files(root)
    checks.append(
        _check_row(
            check_id="docs_markdown_files_found",
            ok=len(files) > 0,
            value={"root": root.as_posix(), "count": len(files)},
            expect="at least one markdown file found",
            mode="enforce",
        )
    )

    decode_failures: list[dict[str, Any]] = []
    suspicious: list[dict[str, Any]] = []
    scanned: list[dict[str, Any]] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except Exception as exc:
            decode_failures.append({"path": path.as_posix(), "error": exc.__class__.__name__})
            continue
        score = _mojibake_score(text)
        row = {
            "path": path.as_posix(),
            **score,
        }
        scanned.append(row)
        if int(score["hint_count"]) >= int(args.min_hint_count) and float(score["ratio"]) >= float(args.min_hint_ratio):
            suspicious.append(row)

    checks.append(
        _check_row(
            check_id="docs_utf8_decode",
            ok=len(decode_failures) == 0,
            value={"failed": len(decode_failures)},
            expect="all markdown files decode with utf-8",
            mode=mode,
        )
    )
    checks.append(
        _check_row(
            check_id="docs_mojibake_suspicious_bound",
            ok=len(suspicious) <= max(0, int(args.max_suspicious_files)),
            value={
                "suspicious": len(suspicious),
                "max_suspicious_files": max(0, int(args.max_suspicious_files)),
                "min_hint_count": max(1, int(args.min_hint_count)),
                "min_hint_ratio": float(args.min_hint_ratio),
            },
            expect="suspicious markdown files within allowed bound",
            mode=mode,
        )
    )

    enforce_rows = [row for row in checks if str(row.get("mode") or "warn") == "enforce"]
    ok = all(bool(row.get("ok")) for row in enforce_rows)

    ended = time.time()
    report = {
        "ok": bool(ok),
        "started_at": round(started, 3),
        "ended_at": round(ended, 3),
        "duration_s": round(ended - started, 3),
        "strict": bool(args.strict),
        "docs_root": root.as_posix(),
        "checks": checks,
        "summary": {
            "files_total": len(files),
            "decode_failures": decode_failures,
            "suspicious_files": suspicious,
            "scanned": scanned,
        },
    }
    out_default = Path(".data/out") / f"doc_encoding_guard_{int(ended)}.json"
    out_path = Path(str(args.out or out_default))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if bool(args.strict):
        return 0 if bool(ok) else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
