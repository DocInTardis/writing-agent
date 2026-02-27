from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from scripts import release_rollout_executor


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _base_policy(tmp_path: Path) -> Path:
    policy = tmp_path / "release_rollout_policy.json"
    _write_json(
        policy,
        {
            "version": 1,
            "channels": {
                "canary": {"min_rollout_percent": 1, "max_rollout_percent": 25},
                "stable": {"required_rollout_percent": 100},
            },
            "history": {
                "min_entries": 0,
                "max_age_s": 2592000,
                "require_reason": True,
                "require_actor": True,
                "allow_initial_equal_without_history": True,
            },
            "promotion": {
                "require_canary_for_stable": True,
                "min_canary_observe_s": 1800,
                "allow_direct_stable_set": False,
                "direct_stable_reason_keywords": ["hotfix", "emergency", "security", "rollback"],
            },
            "stages": {
                "canary": [5, 20, 50],
                "stable": [100],
                "min_stage_observe_s": 30,
            },
            "gates": {
                "required_reports": [
                    {
                        "id": "rollout_guard",
                        "pattern": (tmp_path / "release_rollout_guard_*.json").as_posix(),
                        "max_age_s": 3600,
                        "required": True,
                        "require_ok": True,
                    }
                ]
            },
        },
    )
    return policy


@dataclass
class _Proc:
    returncode: int
    stdout: str = ""
    stderr: str = ""


def test_rollout_executor_dry_run_set_canary(monkeypatch, tmp_path: Path) -> None:
    now = time.time()
    channels = tmp_path / "release_channels.json"
    policy = _base_policy(tmp_path)
    out_path = tmp_path / "release_rollout_executor.json"
    _write_json(
        channels,
        {
            "version": 1,
            "updated_at": now,
            "channels": {
                "canary": {"version": "0.1.0", "rollout_percent": 5, "updated_at": now},
                "stable": {"version": "0.1.0", "rollout_percent": 100, "updated_at": now},
            },
            "history": [],
        },
    )
    _write_json(tmp_path / "release_rollout_guard_1.json", {"ok": True, "ended_at": now})

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "release_rollout_executor.py",
            "--channels-file",
            channels.as_posix(),
            "--policy",
            policy.as_posix(),
            "--target-version",
            "0.1.1",
            "--dry-run",
            "--strict",
            "--out",
            out_path.as_posix(),
        ],
    )
    code = release_rollout_executor.main()
    body = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 0
    assert body["ok"] is True
    assert body["plan"]["action"] == "set_canary"
    assert body["apply_result"]["applied"] is False
    assert str(((body.get("correlation") if isinstance(body.get("correlation"), dict) else {}).get("correlation_id") or ""))
    assert str(
        ((body.get("correlation") if isinstance(body.get("correlation"), dict) else {}).get("release_candidate_id") or "")
    )


def test_rollout_executor_apply_advances_canary_stage(monkeypatch, tmp_path: Path) -> None:
    now = time.time()
    channels = tmp_path / "release_channels.json"
    policy = _base_policy(tmp_path)
    out_path = tmp_path / "release_rollout_executor.json"
    _write_json(
        channels,
        {
            "version": 1,
            "updated_at": now - 200,
            "channels": {
                "canary": {"version": "0.1.1", "rollout_percent": 5, "updated_at": now - 120},
                "stable": {"version": "0.1.0", "rollout_percent": 100, "updated_at": now - 300},
            },
            "history": [
                {
                    "ts": now - 120,
                    "action": "set",
                    "channel": "canary",
                    "from_version": "0.1.0",
                    "to_version": "0.1.1",
                    "reason": "start canary",
                    "actor": "release-bot",
                }
            ],
        },
    )
    _write_json(tmp_path / "release_rollout_guard_1.json", {"ok": True, "ended_at": now})

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "release_rollout_executor.py",
            "--channels-file",
            channels.as_posix(),
            "--policy",
            policy.as_posix(),
            "--target-version",
            "0.1.1",
            "--apply",
            "--strict",
            "--out",
            out_path.as_posix(),
        ],
    )
    code = release_rollout_executor.main()
    body = json.loads(out_path.read_text(encoding="utf-8"))
    store = json.loads(channels.read_text(encoding="utf-8"))
    assert code == 0
    assert body["ok"] is True
    assert body["plan"]["action"] == "rollout_canary"
    assert body["apply_result"]["applied"] is True
    assert int(store["channels"]["canary"]["rollout_percent"]) == 20
    history = store.get("history") if isinstance(store.get("history"), list) else []
    assert history
    assert str((history[-1] if isinstance(history[-1], dict) else {}).get("correlation_id") or "")
    assert str((history[-1] if isinstance(history[-1], dict) else {}).get("release_candidate_id") or "")


def test_rollout_executor_strict_fails_when_required_gate_missing(monkeypatch, tmp_path: Path) -> None:
    now = time.time()
    channels = tmp_path / "release_channels.json"
    policy = _base_policy(tmp_path)
    out_path = tmp_path / "release_rollout_executor.json"
    _write_json(
        channels,
        {
            "version": 1,
            "updated_at": now,
            "channels": {
                "canary": {"version": "0.1.0", "rollout_percent": 5, "updated_at": now},
                "stable": {"version": "0.1.0", "rollout_percent": 100, "updated_at": now},
            },
            "history": [],
        },
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "release_rollout_executor.py",
            "--channels-file",
            channels.as_posix(),
            "--policy",
            policy.as_posix(),
            "--target-version",
            "0.1.1",
            "--strict",
            "--out",
            out_path.as_posix(),
        ],
    )
    code = release_rollout_executor.main()
    body = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 2
    assert body["ok"] is False


def test_rollout_executor_apply_runs_traffic_command(monkeypatch, tmp_path: Path) -> None:
    now = time.time()
    channels = tmp_path / "release_channels.json"
    policy = _base_policy(tmp_path)
    out_path = tmp_path / "release_rollout_executor.json"
    _write_json(
        channels,
        {
            "version": 1,
            "updated_at": now - 200,
            "channels": {
                "canary": {"version": "0.1.1", "rollout_percent": 5, "updated_at": now - 120},
                "stable": {"version": "0.1.0", "rollout_percent": 100, "updated_at": now - 300},
            },
            "history": [
                {
                    "ts": now - 120,
                    "action": "set",
                    "channel": "canary",
                    "from_version": "0.1.0",
                    "to_version": "0.1.1",
                    "reason": "start canary",
                    "actor": "release-bot",
                }
            ],
        },
    )
    _write_json(tmp_path / "release_rollout_guard_1.json", {"ok": True, "ended_at": now})

    seen: dict[str, object] = {}

    def _fake_run(argv, check, text, capture_output, timeout):  # type: ignore[no-untyped-def]
        seen["argv"] = list(argv)
        return _Proc(returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(release_rollout_executor.subprocess, "run", _fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "release_rollout_executor.py",
            "--channels-file",
            channels.as_posix(),
            "--policy",
            policy.as_posix(),
            "--target-version",
            "0.1.1",
            "--apply",
            "--strict",
            "--traffic-apply-command",
            "rolloutctl --action {action} --to {target_version} --canary {canary_rollout_percent} --corr {correlation_id}",
            "--traffic-apply-required",
            "--correlation-id",
            "corr-abc",
            "--release-candidate-id",
            "rc-abc",
            "--out",
            out_path.as_posix(),
        ],
    )
    code = release_rollout_executor.main()
    body = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 0
    assert body["ok"] is True
    traffic = body["apply_result"]["traffic_apply"]
    assert traffic["executed"] is True
    assert traffic["ok"] is True
    assert any("--action" == token for token in traffic["command_argv"])
    assert "corr-abc" in traffic["command_argv"]
    assert "rolloutctl" in str(seen.get("argv", []))
    assert body["correlation"]["correlation_id"] == "corr-abc"
    assert body["correlation"]["release_candidate_id"] == "rc-abc"
    store = json.loads(channels.read_text(encoding="utf-8"))
    history = store.get("history") if isinstance(store.get("history"), list) else []
    assert str((history[-1] if isinstance(history[-1], dict) else {}).get("correlation_id") or "") == "corr-abc"
    assert str((history[-1] if isinstance(history[-1], dict) else {}).get("release_candidate_id") or "") == "rc-abc"


def test_rollout_executor_apply_reverts_on_traffic_command_failure(monkeypatch, tmp_path: Path) -> None:
    now = time.time()
    channels = tmp_path / "release_channels.json"
    policy = _base_policy(tmp_path)
    out_path = tmp_path / "release_rollout_executor.json"
    initial_payload = {
        "version": 1,
        "updated_at": now - 200,
        "channels": {
            "canary": {"version": "0.1.1", "rollout_percent": 5, "updated_at": now - 120},
            "stable": {"version": "0.1.0", "rollout_percent": 100, "updated_at": now - 300},
        },
        "history": [
            {
                "ts": now - 120,
                "action": "set",
                "channel": "canary",
                "from_version": "0.1.0",
                "to_version": "0.1.1",
                "reason": "start canary",
                "actor": "release-bot",
            }
        ],
    }
    _write_json(channels, initial_payload)
    _write_json(tmp_path / "release_rollout_guard_1.json", {"ok": True, "ended_at": now})

    def _fake_run(argv, check, text, capture_output, timeout):  # type: ignore[no-untyped-def]
        return _Proc(returncode=9, stdout="", stderr="fail")

    monkeypatch.setattr(release_rollout_executor.subprocess, "run", _fake_run)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "release_rollout_executor.py",
            "--channels-file",
            channels.as_posix(),
            "--policy",
            policy.as_posix(),
            "--target-version",
            "0.1.1",
            "--apply",
            "--strict",
            "--traffic-apply-command",
            "rolloutctl --action {action} --to {target_version} --canary {canary_rollout_percent}",
            "--traffic-apply-required",
            "--out",
            out_path.as_posix(),
        ],
    )
    code = release_rollout_executor.main()
    body = json.loads(out_path.read_text(encoding="utf-8"))
    restored = json.loads(channels.read_text(encoding="utf-8"))
    assert code == 2
    assert body["ok"] is False
    assert body["apply_result"]["traffic_apply"]["ok"] is False
    assert body["apply_result"]["reverted"] is True
    assert int(restored["channels"]["canary"]["rollout_percent"]) == 5


def test_rollout_executor_strict_fails_when_traffic_required_but_missing(monkeypatch, tmp_path: Path) -> None:
    now = time.time()
    channels = tmp_path / "release_channels.json"
    policy = _base_policy(tmp_path)
    out_path = tmp_path / "release_rollout_executor.json"
    _write_json(
        channels,
        {
            "version": 1,
            "updated_at": now - 200,
            "channels": {
                "canary": {"version": "0.1.1", "rollout_percent": 5, "updated_at": now - 120},
                "stable": {"version": "0.1.0", "rollout_percent": 100, "updated_at": now - 300},
            },
            "history": [
                {
                    "ts": now - 120,
                    "action": "set",
                    "channel": "canary",
                    "from_version": "0.1.0",
                    "to_version": "0.1.1",
                    "reason": "start canary",
                    "actor": "release-bot",
                }
            ],
        },
    )
    _write_json(tmp_path / "release_rollout_guard_1.json", {"ok": True, "ended_at": now})

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "release_rollout_executor.py",
            "--channels-file",
            channels.as_posix(),
            "--policy",
            policy.as_posix(),
            "--target-version",
            "0.1.1",
            "--apply",
            "--strict",
            "--traffic-apply-required",
            "--out",
            out_path.as_posix(),
        ],
    )
    code = release_rollout_executor.main()
    body = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 2
    assert body["ok"] is False
    assert body["apply_result"]["traffic_apply"]["reason"] == "required_command_missing"


def test_rollout_executor_strict_blocks_apply_for_unknown_traffic_placeholder(monkeypatch, tmp_path: Path) -> None:
    now = time.time()
    channels = tmp_path / "release_channels.json"
    policy = _base_policy(tmp_path)
    out_path = tmp_path / "release_rollout_executor.json"
    _write_json(
        channels,
        {
            "version": 1,
            "updated_at": now - 200,
            "channels": {
                "canary": {"version": "0.1.1", "rollout_percent": 5, "updated_at": now - 120},
                "stable": {"version": "0.1.0", "rollout_percent": 100, "updated_at": now - 300},
            },
            "history": [
                {
                    "ts": now - 120,
                    "action": "set",
                    "channel": "canary",
                    "from_version": "0.1.0",
                    "to_version": "0.1.1",
                    "reason": "start canary",
                    "actor": "release-bot",
                }
            ],
        },
    )
    _write_json(tmp_path / "release_rollout_guard_1.json", {"ok": True, "ended_at": now})

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "release_rollout_executor.py",
            "--channels-file",
            channels.as_posix(),
            "--policy",
            policy.as_posix(),
            "--target-version",
            "0.1.1",
            "--apply",
            "--strict",
            "--traffic-apply-command",
            "rolloutctl --action {action} --to {target_version} --bad {unknown_field}",
            "--traffic-apply-required",
            "--out",
            out_path.as_posix(),
        ],
    )
    code = release_rollout_executor.main()
    body = json.loads(out_path.read_text(encoding="utf-8"))
    store = json.loads(channels.read_text(encoding="utf-8"))
    checks = {str(row.get("id")): bool(row.get("ok")) for row in body["checks"]}
    assert code == 2
    assert body["ok"] is False
    assert checks["traffic_apply_template_valid"] is False
    assert body["apply_result"]["applied"] is False
    assert int(store["channels"]["canary"]["rollout_percent"]) == 5
