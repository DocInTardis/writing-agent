from __future__ import annotations

import subprocess
from pathlib import Path

from scripts import incident_notify_drill


def test_build_synthetic_incident_report_shape() -> None:
    report = incident_notify_drill._build_synthetic_incident_report(ts=1700000000.0, level="p1")
    assert report["ok"] is True
    assert report["skipped"] is False
    incident = report["incident"]
    assert incident["escalation_level"] == "p1"
    assert incident["severity"] == "critical"
    assert str(incident["incident_id"]).startswith("INC-DRILL-")


def test_latest_call_helper() -> None:
    calls = [{"path": "/webhook", "x": 1}, {"path": "/slack", "x": 2}, {"path": "/webhook", "x": 3}]
    out = incident_notify_drill._latest_call(calls, "/webhook")
    assert isinstance(out, dict)
    assert out["x"] == 3


def test_build_synthetic_oncall_roster_shape() -> None:
    roster = incident_notify_drill._build_synthetic_oncall_roster(
        ts=1700000000.0,
        webhook_url="http://127.0.0.1:18140/oncall-webhook",
        email="oncall@example.local",
    )
    assert roster["version"] == 1
    primary = roster["primary"]
    assert primary["id"] == "oncall-drill-primary"
    assert primary["webhook_url"].endswith("/oncall-webhook")
    assert primary["email"] == ["oncall@example.local"]


def test_run_notify_includes_oncall_roster_args(monkeypatch, tmp_path: Path) -> None:
    captured: dict[str, object] = {}

    def _fake_run(cmd, check, text, capture_output):  # type: ignore[no-untyped-def]
        captured["cmd"] = list(cmd)
        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(incident_notify_drill.subprocess, "run", _fake_run)
    report_path = tmp_path / "incident_report.json"
    roster_path = tmp_path / "oncall_roster.json"
    out_path = tmp_path / "notify.json"
    proc = incident_notify_drill._run_notify(
        report_path=report_path,
        oncall_roster_path=roster_path,
        host="127.0.0.1",
        port=18140,
        signing_key="drill-secret",
        out_path=out_path,
        timeout_s=5.0,
        with_email=False,
        email_port=18141,
    )
    cmd = captured["cmd"] if isinstance(captured.get("cmd"), list) else []
    assert proc.returncode == 0
    assert "--oncall-roster" in cmd
    assert roster_path.as_posix() in cmd
    assert "--prefer-oncall-roster" in cmd
    assert "1" in cmd
