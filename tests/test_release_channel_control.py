from __future__ import annotations

import json
import sys
from pathlib import Path

from scripts import release_channel_control


def test_semver_validator() -> None:
    assert release_channel_control._is_semver("1.2.3")
    assert release_channel_control._is_semver("1.2.3-rc.1")
    assert not release_channel_control._is_semver("1.2")
    assert not release_channel_control._is_semver("v1.2.3")


def test_validate_store_strict_expected_version_match() -> None:
    store = {
        "version": 1,
        "updated_at": 0,
        "channels": {
            "canary": {"version": "0.2.0", "rollout_percent": 20, "updated_at": 0},
            "stable": {"version": "0.1.9", "rollout_percent": 100, "updated_at": 0},
        },
        "history": [],
    }
    out = release_channel_control._validate_store(store, expected_version="0.2.0", strict=True)
    assert out["ok"] is True


def test_validate_store_strict_rollout_violation() -> None:
    store = {
        "version": 1,
        "updated_at": 0,
        "channels": {
            "canary": {"version": "0.1.0", "rollout_percent": 10, "updated_at": 0},
            "stable": {"version": "0.1.0", "rollout_percent": 80, "updated_at": 0},
        },
        "history": [],
    }
    out = release_channel_control._validate_store(store, expected_version="0.1.0", strict=True)
    assert out["ok"] is False
    checks = out["checks"]
    assert any(row["id"] == "stable_rollout_100" and row["ok"] is False for row in checks)


def test_set_command_audit_strict_failure_returns_non_zero(monkeypatch, tmp_path: Path) -> None:
    channels_path = tmp_path / "release_channels.json"
    channels_path.write_text(
        json.dumps(
            {
                "version": 1,
                "updated_at": 0,
                "channels": {
                    "canary": {"version": "0.1.0", "rollout_percent": 5, "updated_at": 0},
                    "stable": {"version": "0.1.0", "rollout_percent": 100, "updated_at": 0},
                },
                "history": [],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        release_channel_control.audit_chain,
        "record_operation",
        lambda **kwargs: {"ok": False, "error": "audit unavailable"},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "release_channel_control.py",
            "--audit-strict",
            "set",
            "--file",
            channels_path.as_posix(),
            "--channel",
            "canary",
            "--version",
            "1.2.3",
        ],
    )
    code = release_channel_control.main()
    assert code == 2
