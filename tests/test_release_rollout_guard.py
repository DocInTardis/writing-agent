from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from scripts import release_rollout_guard


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_rollout_guard_strict_passes_for_initial_aligned_state(monkeypatch, tmp_path: Path) -> None:
    channels = tmp_path / "release_channels.json"
    policy = tmp_path / "release_rollout_policy.json"
    out_path = tmp_path / "release_rollout_guard.json"

    _write_json(
        channels,
        {
            "version": 1,
            "updated_at": 0.0,
            "channels": {
                "canary": {"version": "0.1.0", "rollout_percent": 5, "updated_at": 0.0},
                "stable": {"version": "0.1.0", "rollout_percent": 100, "updated_at": 0.0},
            },
            "history": [],
        },
    )
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
                "max_age_s": 86400,
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
        },
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "release_rollout_guard.py",
            "--channels-file",
            channels.as_posix(),
            "--policy",
            policy.as_posix(),
            "--strict",
            "--out",
            out_path.as_posix(),
        ],
    )
    code = release_rollout_guard.main()
    body = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 0
    assert body["ok"] is True


def test_rollout_guard_strict_fails_on_direct_stable_set_without_override(monkeypatch, tmp_path: Path) -> None:
    now = time.time()
    channels = tmp_path / "release_channels.json"
    policy = tmp_path / "release_rollout_policy.json"
    out_path = tmp_path / "release_rollout_guard.json"

    _write_json(
        channels,
        {
            "version": 1,
            "updated_at": now,
            "channels": {
                "canary": {"version": "0.1.1", "rollout_percent": 5, "updated_at": now - 600},
                "stable": {"version": "0.1.1", "rollout_percent": 100, "updated_at": now - 200},
            },
            "history": [
                {
                    "ts": now - 600,
                    "action": "set",
                    "channel": "canary",
                    "from_version": "0.1.0",
                    "to_version": "0.1.1",
                    "reason": "canary start",
                    "actor": "release-bot",
                },
                {
                    "ts": now - 200,
                    "action": "set",
                    "channel": "stable",
                    "from_version": "0.1.0",
                    "to_version": "0.1.1",
                    "reason": "regular promote",
                    "actor": "release-bot",
                },
            ],
        },
    )
    _write_json(
        policy,
        {
            "version": 1,
            "channels": {
                "canary": {"min_rollout_percent": 1, "max_rollout_percent": 25},
                "stable": {"required_rollout_percent": 100},
            },
            "history": {
                "min_entries": 1,
                "max_age_s": 86400,
                "require_reason": True,
                "require_actor": True,
                "allow_initial_equal_without_history": False,
            },
            "promotion": {
                "require_canary_for_stable": True,
                "min_canary_observe_s": 60,
                "allow_direct_stable_set": False,
                "direct_stable_reason_keywords": ["hotfix", "emergency", "security", "rollback"],
            },
        },
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "release_rollout_guard.py",
            "--channels-file",
            channels.as_posix(),
            "--policy",
            policy.as_posix(),
            "--strict",
            "--out",
            out_path.as_posix(),
        ],
    )
    code = release_rollout_guard.main()
    body = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 2
    assert body["ok"] is False
    checks = body.get("checks", [])
    assert any(row["id"] == "direct_stable_set_allowed" and row["ok"] is False for row in checks)


def test_rollout_guard_non_strict_does_not_block(monkeypatch, tmp_path: Path) -> None:
    channels = tmp_path / "release_channels.json"
    policy = tmp_path / "release_rollout_policy.json"
    out_path = tmp_path / "release_rollout_guard.json"

    _write_json(
        channels,
        {
            "version": 1,
            "updated_at": 0.0,
            "channels": {
                "canary": {"version": "0.1.0", "rollout_percent": 70, "updated_at": 0.0},
                "stable": {"version": "0.1.0", "rollout_percent": 100, "updated_at": 0.0},
            },
            "history": [],
        },
    )
    _write_json(
        policy,
        {
            "version": 1,
            "channels": {
                "canary": {"min_rollout_percent": 1, "max_rollout_percent": 25},
                "stable": {"required_rollout_percent": 100},
            },
            "history": {"min_entries": 0, "max_age_s": 86400},
            "promotion": {"require_canary_for_stable": True},
        },
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "release_rollout_guard.py",
            "--channels-file",
            channels.as_posix(),
            "--policy",
            policy.as_posix(),
            "--out",
            out_path.as_posix(),
        ],
    )
    code = release_rollout_guard.main()
    body = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 0
    assert body["ok"] is False
