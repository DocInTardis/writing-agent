from __future__ import annotations

import json
import sys
from pathlib import Path

from scripts import incident_config_guard


def test_extract_policy_channels() -> None:
    policy = {
        "default_channels": ["webhook"],
        "rules": [
            {"channels": ["slack", "email"]},
            {"channels": ["feishu"]},
        ],
    }
    channels = incident_config_guard._extract_policy_channels(policy)
    assert channels == {"webhook", "slack", "email", "feishu"}


def test_main_strict_passes_with_valid_config(monkeypatch, tmp_path: Path) -> None:
    policy_path = tmp_path / "incident_routing.json"
    policy_path.write_text(
        json.dumps({"default_channels": ["webhook"], "rules": [{"channels": ["slack", "email"]}]}),
        encoding="utf-8",
    )
    out_path = tmp_path / "incident_config_guard.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "incident_config_guard.py",
            "--strict",
            "--routing-policy",
            policy_path.as_posix(),
            "--webhook-url",
            "http://example.invalid/hook",
            "--out",
            out_path.as_posix(),
        ],
    )
    code = incident_config_guard.main()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 0
    assert data["ok"] is True


def test_main_fails_on_unknown_policy_channel(monkeypatch, tmp_path: Path) -> None:
    policy_path = tmp_path / "incident_routing.json"
    policy_path.write_text(
        json.dumps({"default_channels": ["webhook"], "rules": [{"channels": ["pagerduty"]}]}),
        encoding="utf-8",
    )
    out_path = tmp_path / "incident_config_guard.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "incident_config_guard.py",
            "--strict",
            "--routing-policy",
            policy_path.as_posix(),
            "--webhook-url",
            "http://example.invalid/hook",
            "--out",
            out_path.as_posix(),
        ],
    )
    code = incident_config_guard.main()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 2
    assert data["ok"] is False


def test_main_require_oncall_roster_fails_when_missing(monkeypatch, tmp_path: Path) -> None:
    policy_path = tmp_path / "incident_routing.json"
    policy_path.write_text(json.dumps({"default_channels": ["webhook"], "rules": []}), encoding="utf-8")
    out_path = tmp_path / "incident_config_guard.json"
    missing_roster = tmp_path / "missing_oncall_roster.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "incident_config_guard.py",
            "--routing-policy",
            policy_path.as_posix(),
            "--webhook-url",
            "http://example.invalid/hook",
            "--oncall-roster",
            missing_roster.as_posix(),
            "--require-oncall-roster",
            "--out",
            out_path.as_posix(),
        ],
    )
    code = incident_config_guard.main()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    checks = {str(row.get("id")): row for row in data.get("checks", []) if isinstance(row, dict)}
    assert code == 2
    assert data["ok"] is False
    assert checks["oncall_roster_loaded"]["ok"] is False
    assert checks["oncall_target_present"]["ok"] is False


def test_main_require_oncall_roster_passes_with_target(monkeypatch, tmp_path: Path) -> None:
    policy_path = tmp_path / "incident_routing.json"
    policy_path.write_text(json.dumps({"default_channels": ["webhook"], "rules": []}), encoding="utf-8")
    roster_path = tmp_path / "oncall_roster.json"
    roster_path.write_text(
        json.dumps(
            {
                "version": 1,
                "primary": {
                    "id": "oncall-primary",
                    "email": ["oncall@example.local"],
                },
            }
        ),
        encoding="utf-8",
    )
    out_path = tmp_path / "incident_config_guard.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "incident_config_guard.py",
            "--strict",
            "--routing-policy",
            policy_path.as_posix(),
            "--webhook-url",
            "http://example.invalid/hook",
            "--oncall-roster",
            roster_path.as_posix(),
            "--require-oncall-roster",
            "--out",
            out_path.as_posix(),
        ],
    )
    code = incident_config_guard.main()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    checks = {str(row.get("id")): row for row in data.get("checks", []) if isinstance(row, dict)}
    assert code == 0
    assert data["ok"] is True
    assert checks["oncall_roster_loaded"]["ok"] is True
    assert checks["oncall_target_present"]["ok"] is True
