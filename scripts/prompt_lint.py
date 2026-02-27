"""Prompt Lint command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from writing_agent.v2.prompt_registry import prompt_schema_valid


FORBIDDEN = ("jailbreak", "ignore all", "bypass")


def lint_prompt(prompt: dict) -> list[str]:
    issues: list[str] = []
    if not prompt_schema_valid(prompt):
        issues.append("schema_missing_required_layers")
        return issues
    for key in ("system", "developer", "task", "style", "citation"):
        text = str(prompt.get(key) or "").strip()
        if not text:
            issues.append(f"empty_layer:{key}")
        if len(text) > 4000:
            issues.append(f"layer_too_long:{key}")
        low = text.lower()
        for bad in FORBIDDEN:
            if bad in low:
                issues.append(f"forbidden_token:{key}:{bad}")
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lint prompt registry payloads")
    parser.add_argument("--file", default=".data/prompt_registry/prompts.json")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)

    path = Path(args.file)
    if not path.exists():
        print(json.dumps({"ok": True, "checked": 0, "issues": []}, ensure_ascii=False, indent=2))
        return 0

    raw = json.loads(path.read_text(encoding="utf-8"))
    prompts = raw.get("prompts") if isinstance(raw.get("prompts"), dict) else {}
    all_issues: list[dict] = []
    checked = 0
    for prompt_id, variants in prompts.items():
        if not isinstance(variants, list):
            continue
        for row in variants:
            if not isinstance(row, dict):
                continue
            checked += 1
            payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
            issues = lint_prompt(payload)
            for issue in issues:
                all_issues.append({"prompt_id": prompt_id, "version": row.get("version"), "issue": issue})

    report = {"ok": len(all_issues) == 0, "checked": checked, "issues": all_issues}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.strict and all_issues:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
