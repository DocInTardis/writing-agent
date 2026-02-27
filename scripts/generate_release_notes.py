#!/usr/bin/env python3
"""Generate Release Notes command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path


_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


def _is_semver(value: str) -> bool:
    return bool(_SEMVER_RE.match(str(value or "").strip()))


def _sanitize_release_version(value: str) -> str:
    text = str(value or "").strip().replace("/", "_").replace("\\", "_").replace(" ", "_")
    return re.sub(r"[^0-9A-Za-z._-]+", "_", text)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate release notes markdown from changelog snapshot.")
    parser.add_argument("--release-version", required=True)
    parser.add_argument("--changes-file", default="CHANGES.md")
    parser.add_argument("--max-lines", type=int, default=80)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    started = time.time()
    release_version = str(args.release_version or "").strip()
    changes_path = Path(str(args.changes_file))

    lines: list[str] = []
    if changes_path.exists():
        try:
            lines = changes_path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            lines = []
    excerpt_count = max(10, int(args.max_lines))
    excerpt = lines[:excerpt_count]

    notes = [
        f"# Release {release_version}",
        "",
        f"Generated at: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(started))}",
        "",
        "## Summary",
        f"- Release version: `{release_version}`",
        f"- Changelog source: `{changes_path.as_posix()}`",
        "",
        "## Changelog Snapshot",
        "```text",
        *excerpt,
        "```",
        "",
        "## Validation Checklist",
        "- [ ] release preflight passed",
        "- [ ] rollback bundle generated",
        "- [ ] migration assistant report reviewed",
        "- [ ] audit chain verification passed",
    ]
    note_text = "\n".join(notes).rstrip() + "\n"

    safe_version = _sanitize_release_version(release_version or "unknown")
    default_out = Path(".data/out") / f"release_notes_{safe_version}_{int(started)}.md"
    out_path = Path(str(args.out or default_out))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(note_text, encoding="utf-8")

    ok = _is_semver(release_version) and out_path.exists()
    report = {
        "ok": bool(ok),
        "release_version": release_version,
        "changes_file": changes_path.as_posix(),
        "out_path": out_path.as_posix(),
        "excerpt_lines": len(excerpt),
        "generated_at": round(time.time(), 3),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if bool(ok) else 2


if __name__ == "__main__":
    raise SystemExit(main())
