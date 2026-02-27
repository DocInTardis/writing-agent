#!/usr/bin/env python3
"""Generate Release Manifest command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any

VERSION_RE = re.compile(r'__version__\s*=\s*"([^"]+)"')
SCHEMA_FIELD_RE = re.compile(r'schema_version\s*=\s*"([^"]+)"')


def _load_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def _extract_app_version(init_text: str) -> str:
    m = VERSION_RE.search(str(init_text or ""))
    return str(m.group(1)).strip() if m else ""


def _extract_schema_version(context_text: str) -> str:
    m = SCHEMA_FIELD_RE.search(str(context_text or ""))
    return str(m.group(1)).strip() if m else ""


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _git(cmd: list[str]) -> str:
    try:
        proc = subprocess.run(["git", *cmd], capture_output=True, text=True, check=False)
    except Exception:
        return ""
    if int(proc.returncode) != 0:
        return ""
    return str(proc.stdout or "").strip()


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_text(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return raw if isinstance(raw, dict) else None


def _latest_paths(pattern: str, *, recent: int) -> list[Path]:
    rows = sorted((Path(p) for p in glob.glob(pattern)), key=lambda p: p.stat().st_mtime if p.exists() else 0.0)
    take = max(1, int(recent))
    return rows[-take:]


def _pattern_key(pattern: str) -> str:
    name = Path(str(pattern)).name
    name = re.sub(r"\*+", "", name)
    name = re.sub(r"\.json$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"_+$", "", name)
    return name or "gate"


def _derive_release_candidate_id(*, release_candidate_id: str, app_version: str, git_commit: str, generated_at_ts: int) -> str:
    raw = str(release_candidate_id or "").strip()
    if raw:
        return raw
    commit_short = str(git_commit or "").strip()[:12]
    version = str(app_version or "").strip() or "unknown"
    if commit_short:
        return f"rc-{version}-{commit_short}"
    return f"rc-{version}-{int(generated_at_ts)}"


def _gate_evidence_entry(path: Path) -> dict[str, Any]:
    exists = path.exists()
    row: dict[str, Any] = {
        "path": path.as_posix(),
        "exists": bool(exists),
        "size": int(path.stat().st_size) if exists else 0,
        "sha256": _sha256_file(path) if exists else "",
    }
    raw = _load_json(path) if exists else None
    if isinstance(raw, dict):
        ts = float(raw.get("ended_at") or raw.get("generated_at") or raw.get("started_at") or 0.0)
        row["ts"] = round(ts, 3) if ts > 0 else 0.0
        row["ok"] = bool(raw.get("ok")) if "ok" in raw else None
        correlation = raw.get("correlation") if isinstance(raw.get("correlation"), dict) else {}
        row["release_candidate_id"] = str(
            raw.get("release_candidate_id")
            or correlation.get("release_candidate_id")
            or ""
        ).strip()
        row["correlation_id"] = str(
            raw.get("correlation_id")
            or correlation.get("correlation_id")
            or ""
        ).strip()
    return row


def _build_gate_evidence_map(
    *,
    release_candidate_id: str,
    patterns: list[str],
    recent: int,
) -> tuple[dict[str, Any], list[str]]:
    evidence: dict[str, Any] = {}
    missing: list[str] = []
    for pattern in patterns:
        key = _pattern_key(pattern)
        paths = _latest_paths(pattern, recent=recent)
        rows = [_gate_evidence_entry(path) for path in paths]
        if not rows:
            missing.append(key)
        evidence[key] = {"pattern": str(pattern), "rows": rows}
    canonical = _canonical_json(evidence)
    payload = {
        "release_candidate_id": str(release_candidate_id or "").strip(),
        "generated_at": round(time.time(), 3),
        "evidence": evidence,
        "evidence_sha256": _sha256_text(canonical),
    }
    return payload, missing


def _artifact_entry(path: Path, *, required: bool) -> dict[str, Any]:
    exists = path.exists()
    row: dict[str, Any] = {
        "path": path.as_posix(),
        "required": bool(required),
        "exists": bool(exists),
        "size": int(path.stat().st_size) if exists else 0,
    }
    if exists:
        row["sha256"] = _sha256_file(path)
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate release manifest for traceability and rollback records.")
    parser.add_argument("--init-file", default="writing_agent/__init__.py")
    parser.add_argument("--state-context-file", default="writing_agent/state_engine/context.py")
    parser.add_argument("--sbom-manifest", default=".data/out/sbom/sbom-manifest.json")
    parser.add_argument("--baseline", default="security/dependency_baseline.json")
    parser.add_argument("--policy", default="security/release_policy.json")
    parser.add_argument("--release-candidate-id", default="")
    parser.add_argument("--gate-evidence-pattern", action="append", default=[])
    parser.add_argument("--gate-evidence-recent", type=int, default=1)
    parser.add_argument("--require-gate-evidence", action="store_true")
    parser.add_argument("--out", default="")
    parser.add_argument("--require-clean-git", action="store_true")
    parser.add_argument("--artifact", action="append", default=[])
    args = parser.parse_args()

    started = time.time()
    init_path = Path(str(args.init_file))
    state_path = Path(str(args.state_context_file))
    sbom_manifest_path = Path(str(args.sbom_manifest))
    baseline_path = Path(str(args.baseline))
    policy_path = Path(str(args.policy))

    app_version = _extract_app_version(_load_text(init_path))
    schema_version = _extract_schema_version(_load_text(state_path))
    git_commit = _git(["rev-parse", "HEAD"])
    git_branch = _git(["rev-parse", "--abbrev-ref", "HEAD"])
    git_status = _git(["status", "--porcelain"])
    dirty = bool(str(git_status or "").strip())

    required_artifacts = [
        Path("requirements.txt"),
        Path("requirements-dev.txt"),
        Path("writing_agent/web/frontend_svelte/package-lock.json"),
        Path(".github/workflows/release-preflight.yml"),
        Path(".github/workflows/public-release.yml"),
        Path(".github/workflows/dependency-security.yml"),
        baseline_path,
        policy_path,
        Path("security/ops_rbac_policy.json"),
        Path("security/rollback_drill_signature_policy.json"),
        Path("security/oncall_roster.json"),
        Path("security/data_classification_policy.json"),
        Path("security/artifact_schema_catalog_policy.json"),
        Path("security/docs_reality_policy.json"),
        Path("security/public_release_policy.json"),
        Path("security/release_rollout_policy.json"),
        Path("security/release_traffic_adapter_contract.json"),
        Path("security/release_compat_matrix.json"),
    ]
    optional_artifacts = [
        sbom_manifest_path,
        Path("docs/RELEASE_AND_ROLLBACK.md"),
        Path("docs/DEPENDENCY_BASELINE_POLICY.md"),
        Path("docs/RELEASE_CHANNELS.md"),
        Path("docs/RELEASE_ENGINEERING.md"),
        Path("docs/ROLLBACK_DRILL_SIGNATURE.md"),
        Path("docs/START_HERE.md"),
        Path("docs/TROUBLESHOOTING_DECISION_TREE.md"),
        Path("docs/ARTIFACT_SCHEMA_CATALOG.md"),
        Path("docs/PRIVACY_DATA_CLASSIFICATION.md"),
        Path("docs/PUBLIC_RELEASE_PIPELINE.md"),
        Path("docs/MIGRATION_ASSISTANT.md"),
    ]
    extra = [Path(str(x)) for x in list(args.artifact or []) if str(x).strip()]
    for p in extra:
        if p not in required_artifacts and p not in optional_artifacts:
            optional_artifacts.append(p)

    artifacts = [_artifact_entry(p, required=True) for p in required_artifacts]
    artifacts.extend(_artifact_entry(p, required=False) for p in optional_artifacts)

    missing_required = [row.get("path") for row in artifacts if bool(row.get("required")) and not bool(row.get("exists"))]

    default_gate_patterns = [
        ".data/out/release_preflight_*.json",
        ".data/out/release_governance_*.json",
        ".data/out/release_compat_matrix_*.json",
        ".data/out/release_rollout_adapter_contract_*.json",
        ".data/out/release_rollout_guard_*.json",
        ".data/out/release_rollout_executor_*.json",
        ".data/out/rollback_drill_guard_*.json",
        ".data/out/rollback_drill_signature_*.json",
        ".data/out/preflight_trend_guard_*.json",
        ".data/out/capacity_guard_*.json",
        ".data/out/capacity_forecast_*.json",
        ".data/out/doc_encoding_guard_*.json",
        ".data/out/docs_reality_guard_*.json",
        ".data/out/data_classification_guard_*.json",
        ".data/out/artifact_schema_catalog_guard_*.json",
        ".data/out/public_release_guard_*.json",
        ".data/out/migration_assistant_*.json",
        ".data/out/audit_chain_verify_*.json",
    ]
    gate_patterns = [str(item).strip() for item in list(args.gate_evidence_pattern or []) if str(item).strip()]
    if not gate_patterns:
        gate_patterns = list(default_gate_patterns)
    gate_recent = max(1, int(args.gate_evidence_recent))
    release_candidate_id = _derive_release_candidate_id(
        release_candidate_id=str(args.release_candidate_id or ""),
        app_version=app_version,
        git_commit=git_commit,
        generated_at_ts=int(started),
    )
    gate_evidence_map, missing_gate_evidence = _build_gate_evidence_map(
        release_candidate_id=release_candidate_id,
        patterns=gate_patterns,
        recent=gate_recent,
    )

    ok = len(missing_required) == 0
    if bool(args.require_gate_evidence) and len(missing_gate_evidence) > 0:
        ok = False
    if bool(args.require_clean_git) and dirty:
        ok = False

    ended = time.time()
    manifest = {
        "version": 1,
        "generated_at": round(ended, 3),
        "duration_s": round(ended - started, 3),
        "app": {
            "version": app_version,
            "state_schema_version": schema_version,
            "release_candidate_id": release_candidate_id,
        },
        "git": {
            "commit": git_commit,
            "branch": git_branch,
            "dirty": dirty,
        },
        "inputs": {
            "init_file": init_path.as_posix(),
            "state_context_file": state_path.as_posix(),
            "sbom_manifest": sbom_manifest_path.as_posix(),
            "baseline": baseline_path.as_posix(),
            "policy": policy_path.as_posix(),
            "gate_evidence_patterns": gate_patterns,
            "gate_evidence_recent": gate_recent,
        },
        "artifacts": artifacts,
        "gate_evidence_map": {
            release_candidate_id: gate_evidence_map,
        },
        "checks": {
            "missing_required": missing_required,
            "missing_gate_evidence": missing_gate_evidence,
            "require_gate_evidence": bool(args.require_gate_evidence),
            "require_clean_git": bool(args.require_clean_git),
        },
        "ok": bool(ok),
    }
    out_default = Path(".data/out") / f"release_manifest_{int(ended)}.json"
    out_path = Path(str(args.out or out_default))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0 if bool(ok) else 2


if __name__ == "__main__":
    raise SystemExit(main())
