from __future__ import annotations

import json
import sys
from pathlib import Path

from scripts import release_rollout_adapter_contract_check


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _base_contract() -> dict:
    return {
        "version": 1,
        "placeholders": {
            "allowed": [
                "action",
                "target_version",
                "correlation_id",
                "release_candidate_id",
                "canary_rollout_percent",
                "stable_rollout_percent",
            ],
            "required": ["action", "target_version"],
            "recommended": ["correlation_id", "release_candidate_id"],
        },
        "rules": {
            "require_examples": True,
        },
        "adapters": [
            {
                "id": "adapter_a",
                "command_template": "rolloutctl --action {action} --to {target_version} --canary {canary_rollout_percent} --stable {stable_rollout_percent}",
                "required_placeholders": ["canary_rollout_percent", "stable_rollout_percent"],
            }
        ],
    }


def test_rollout_adapter_contract_check_strict_passes(monkeypatch, tmp_path: Path) -> None:
    contract = tmp_path / "contract.json"
    out_path = tmp_path / "adapter_report.json"
    _write_json(contract, _base_contract())
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "release_rollout_adapter_contract_check.py",
            "--contract",
            contract.as_posix(),
            "--strict",
            "--require-runtime-command",
            "--command-template",
            "rolloutctl --action {action} --to {target_version} --corr {correlation_id} --rc {release_candidate_id}",
            "--out",
            out_path.as_posix(),
        ],
    )
    code = release_rollout_adapter_contract_check.main()
    body = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 0
    assert body["ok"] is True


def test_rollout_adapter_contract_check_strict_fails_for_unknown_runtime_placeholder(
    monkeypatch, tmp_path: Path
) -> None:
    contract = tmp_path / "contract.json"
    out_path = tmp_path / "adapter_report.json"
    _write_json(contract, _base_contract())
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "release_rollout_adapter_contract_check.py",
            "--contract",
            contract.as_posix(),
            "--strict",
            "--require-runtime-command",
            "--command-template",
            "rolloutctl --action {action} --to {target_version} --bad {unknown_field}",
            "--out",
            out_path.as_posix(),
        ],
    )
    code = release_rollout_adapter_contract_check.main()
    body = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 2
    assert body["ok"] is False
    checks = {str(row.get("id")): bool(row.get("ok")) for row in body["checks"]}
    assert checks["runtime_command_template_valid"] is False
