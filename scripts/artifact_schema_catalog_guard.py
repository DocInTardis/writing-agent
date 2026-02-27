#!/usr/bin/env python3
"""Artifact Schema Catalog Guard command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import argparse
import glob
import json
import time
from pathlib import Path
from typing import Any


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


def _latest_file(pattern: str) -> Path | None:
    rows = sorted((Path(p) for p in glob.glob(pattern)), key=lambda p: p.stat().st_mtime if p.exists() else 0.0)
    if not rows:
        return None
    return rows[-1]


def _path_exists(raw: dict[str, Any], dotted: str) -> bool:
    node: Any = raw
    for part in [x.strip() for x in str(dotted or "").split(".") if str(x).strip()]:
        if not isinstance(node, dict):
            return False
        if part not in node:
            return False
        node = node.get(part)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate artifact schema catalog coverage and field references.")
    parser.add_argument("--policy", default="security/artifact_schema_catalog_policy.json")
    parser.add_argument("--catalog", default="docs/ARTIFACT_SCHEMA_CATALOG.md")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--require-evidence", action="store_true")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    started = time.time()
    policy_path = Path(str(args.policy))
    catalog_path = Path(str(args.catalog))
    policy = _load_json_dict(policy_path)
    catalog_text = ""
    try:
        catalog_text = catalog_path.read_text(encoding="utf-8")
    except Exception:
        catalog_text = ""

    checks: list[dict[str, Any]] = []
    checks.append(
        _check_row(
            check_id="policy_loaded",
            ok=bool(policy),
            value=policy_path.as_posix(),
            expect="artifact schema catalog policy exists and is valid",
            mode="enforce",
        )
    )
    checks.append(
        _check_row(
            check_id="catalog_loaded",
            ok=bool(catalog_text.strip()),
            value=catalog_path.as_posix(),
            expect="artifact schema catalog markdown exists and is non-empty",
            mode="enforce",
        )
    )

    entries = policy.get("entries") if isinstance(policy.get("entries"), list) else []
    summary_rows: list[dict[str, Any]] = []
    for index, item in enumerate(entries, start=1):
        if not isinstance(item, dict):
            continue
        entry_id = str(item.get("id") or f"entry_{index}").strip() or f"entry_{index}"
        pattern = str(item.get("artifact_glob") or "").strip()
        required_fields = [str(x).strip() for x in (item.get("required_fields") if isinstance(item.get("required_fields"), list) else []) if str(x).strip()]

        checks.append(
            _check_row(
                check_id=f"catalog_has_entry_{entry_id}",
                ok=entry_id in catalog_text,
                value={"entry_id": entry_id},
                expect="catalog should contain entry id marker",
                mode="enforce",
            )
        )
        checks.append(
            _check_row(
                check_id=f"catalog_has_pattern_{entry_id}",
                ok=pattern in catalog_text,
                value={"artifact_glob": pattern},
                expect="catalog should include artifact glob",
                mode="enforce",
            )
        )

        missing_doc_fields: list[str] = []
        for field in required_fields:
            if f"`{field}`" in catalog_text or field in catalog_text:
                continue
            missing_doc_fields.append(field)
        checks.append(
            _check_row(
                check_id=f"catalog_has_required_fields_{entry_id}",
                ok=len(missing_doc_fields) == 0,
                value={"missing_fields": missing_doc_fields},
                expect="catalog should mention all required fields",
                mode="enforce",
            )
        )

        evidence_path = _latest_file(pattern)
        evidence_raw = _load_json_dict(evidence_path) if isinstance(evidence_path, Path) else {}
        checks.append(
            _check_row(
                check_id=f"evidence_exists_{entry_id}",
                ok=isinstance(evidence_path, Path),
                value={"artifact_glob": pattern, "latest": evidence_path.as_posix() if isinstance(evidence_path, Path) else ""},
                expect="latest evidence artifact exists",
                mode="enforce" if bool(args.require_evidence) else "warn",
            )
        )
        if isinstance(evidence_path, Path) and evidence_raw:
            missing_in_evidence = [field for field in required_fields if not _path_exists(evidence_raw, field)]
            checks.append(
                _check_row(
                    check_id=f"evidence_required_fields_{entry_id}",
                    ok=len(missing_in_evidence) == 0,
                    value={"missing_fields": missing_in_evidence},
                    expect="evidence json should contain required fields",
                    mode="enforce" if bool(args.strict) else "warn",
                )
            )
        summary_rows.append(
            {
                "id": entry_id,
                "artifact_glob": pattern,
                "required_fields": required_fields,
                "latest_evidence": evidence_path.as_posix() if isinstance(evidence_path, Path) else "",
            }
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
        "require_evidence": bool(args.require_evidence),
        "policy_file": policy_path.as_posix(),
        "catalog_file": catalog_path.as_posix(),
        "entries": summary_rows,
        "checks": checks,
    }

    out_default = Path(".data/out") / f"artifact_schema_catalog_guard_{int(ended)}.json"
    out_path = Path(str(args.out or out_default))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if bool(report.get("ok")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
