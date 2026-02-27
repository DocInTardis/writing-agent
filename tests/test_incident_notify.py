from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from scripts import incident_notify


def test_parse_csv_dedup() -> None:
    rows = incident_notify._parse_csv("a@example.com, b@example.com, a@example.com")
    assert rows == ["a@example.com", "b@example.com"]


def test_signature_headers() -> None:
    body = b'{"ok":1}'
    headers = incident_notify._signature_headers(body=body, signing_key="secret", ts=1700000000)
    assert headers["X-WA-Timestamp"] == "1700000000"
    assert headers["X-WA-Signature"].startswith("sha256=")


def test_format_brief_contains_core_fields() -> None:
    payload = {
        "report_path": ".data/out/incident_report_1.json",
        "incident": {
            "incident_id": "INC-1",
            "title": "citation issue",
            "severity": "critical",
            "escalation_level": "p1",
            "status": "open",
            "owner": "oncall",
        },
    }
    text = incident_notify._format_brief(payload)
    assert "INC-1" in text
    assert "citation issue" in text
    assert "severity=critical" in text


def test_notify_http_with_retry_returns_attempts(monkeypatch) -> None:
    calls = {"n": 0}

    def _fake(*, url, body, timeout_s, signing_key):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        if calls["n"] == 1:
            return False, {"status": "http_500", "status_code": 500, "ok": False}
        return True, {"status": "http_200", "status_code": 200, "ok": True}

    monkeypatch.setattr(incident_notify, "_http_post_json", _fake)
    out = incident_notify._notify_http_with_retry(
        channel="webhook",
        url="http://example.invalid",
        body={"x": 1},
        timeout_s=1.0,
        retries=2,
        retry_backoff_s=0.0,
        signing_key="",
    )
    assert out["ok"] is True
    assert len(out["attempts"]) == 2


def test_latest_incident_report_prefers_canonical(monkeypatch) -> None:
    def _fake(pattern: str):  # type: ignore[no-untyped-def]
        if pattern == ".data/out/incident_report_[0-9]*.json":
            from pathlib import Path

            return Path(".data/out/incident_report_123.json")
        return None

    monkeypatch.setattr(incident_notify, "_latest_report", _fake)
    out = incident_notify._latest_incident_report()
    assert out is not None
    assert out.as_posix().endswith("incident_report_123.json")


def test_routing_targets_by_severity_and_default() -> None:
    policy = {
        "default_channels": ["webhook"],
        "rules": [
            {
                "id": "high_or_above",
                "enabled": True,
                "min_severity": "high",
                "channels": ["slack", "email"],
            }
        ],
    }
    configured = {"webhook", "slack", "email"}
    high = incident_notify._routing_targets(
        routing_policy=policy,
        incident={"severity": "critical", "owner": "oncall"},
        configured=configured,
    )
    low = incident_notify._routing_targets(
        routing_policy=policy,
        incident={"severity": "low", "owner": "oncall"},
        configured=configured,
    )
    assert high == {"slack", "email"}
    assert low == {"webhook"}


def test_routing_targets_honors_time_window() -> None:
    policy = {
        "default_channels": ["webhook"],
        "rules": [
            {
                "id": "business_hours",
                "enabled": True,
                "min_severity": "high",
                "days_of_week": [0],
                "hours_utc": {"start": 9, "end": 11},
                "channels": ["slack"],
            }
        ],
    }
    configured = {"webhook", "slack"}
    ts_in = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc).timestamp()  # Monday
    ts_out = datetime(2024, 1, 1, 22, 0, 0, tzinfo=timezone.utc).timestamp()  # Monday
    in_window = incident_notify._routing_targets(
        routing_policy=policy,
        incident={"severity": "high", "owner": "oncall", "created_at": ts_in},
        configured=configured,
    )
    out_window = incident_notify._routing_targets(
        routing_policy=policy,
        incident={"severity": "high", "owner": "oncall", "created_at": ts_out},
        configured=configured,
    )
    assert in_window == {"slack"}
    assert out_window == {"webhook"}


def test_dead_letter_write_creates_payload(tmp_path: Path) -> None:
    out = incident_notify._dead_letter_write(
        dead_letter_dir=tmp_path,
        payload={"incident": {"incident_id": "INC-1"}},
        reason="channel_failed",
        channels=[{"channel": "webhook", "ok": False}],
    )
    assert out.exists()
    raw = json.loads(out.read_text(encoding="utf-8"))
    assert raw["reason"] == "channel_failed"
    assert raw["payload"]["incident"]["incident_id"] == "INC-1"


def test_main_writes_dead_letter_on_notify_failure(monkeypatch, tmp_path: Path) -> None:
    report = tmp_path / "incident_report_1.json"
    report.write_text(
        json.dumps({"incident": {"incident_id": "INC-1", "severity": "critical", "escalation_level": "p1"}}),
        encoding="utf-8",
    )
    out_path = tmp_path / "incident_notify.json"
    dead_dir = tmp_path / "dead_letter"

    def _fake_notify_once(**kwargs):  # type: ignore[no-untyped-def]
        return ([{"channel": "webhook", "ok": False, "status": "http_500", "attempts": []}], ["webhook"])

    monkeypatch.setattr(incident_notify, "_notify_once", _fake_notify_once)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "incident_notify.py",
            "--incident-report",
            report.as_posix(),
            "--webhook-url",
            "http://example.invalid/webhook",
            "--dead-letter-dir",
            dead_dir.as_posix(),
            "--out",
            out_path.as_posix(),
        ],
    )
    code = incident_notify.main()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 2
    assert data["ok"] is False
    assert Path(str(data["dead_letter_path"])).exists()


def test_main_replay_dead_letter_mode(monkeypatch, tmp_path: Path) -> None:
    dead_file = tmp_path / "incident_notify_dead_letter_1.json"
    dead_file.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "reason": "channel_failed",
                "payload": {
                    "schema_version": 1,
                    "report_path": ".data/out/incident_report_10.json",
                    "incident": {
                        "incident_id": "INC-R1",
                        "severity": "high",
                        "escalation_level": "p2",
                        "owner": "oncall",
                    },
                    "brief": "x",
                },
                "channels": [],
            }
        ),
        encoding="utf-8",
    )
    out_path = tmp_path / "replay_notify.json"
    seen: dict[str, object] = {}

    def _fake_notify_once(**kwargs):  # type: ignore[no-untyped-def]
        seen["payload"] = kwargs.get("payload")
        return ([{"channel": "webhook", "ok": True, "status": "http_200", "attempts": []}], ["webhook"])

    monkeypatch.setattr(incident_notify, "_notify_once", _fake_notify_once)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "incident_notify.py",
            "--replay-dead-letter",
            dead_file.as_posix(),
            "--webhook-url",
            "http://example.invalid/webhook",
            "--out",
            out_path.as_posix(),
        ],
    )
    code = incident_notify.main()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 0
    assert data["ok"] is True
    assert data["mode"] == "replay"
    payload = seen.get("payload") if isinstance(seen.get("payload"), dict) else {}
    assert str((payload.get("incident") if isinstance(payload.get("incident"), dict) else {}).get("incident_id")) == "INC-R1"


def test_oncall_target_prefers_primary_over_rotation() -> None:
    roster = {
        "primary": {"id": "p", "webhook_url": "http://primary.invalid"},
        "rotations": [{"id": "r1", "active": True, "webhook_url": "http://rotation.invalid"}],
    }
    out = incident_notify._oncall_target_from_roster(roster)
    assert out.get("id") == "p"
    assert out.get("webhook_url") == "http://primary.invalid"


def test_main_uses_oncall_roster_target_when_enabled(monkeypatch, tmp_path: Path) -> None:
    incident_path = tmp_path / "incident_report_1.json"
    incident_path.write_text(
        json.dumps({"incident": {"incident_id": "INC-ONCALL-1", "severity": "critical", "escalation_level": "p1"}}),
        encoding="utf-8",
    )
    roster_path = tmp_path / "oncall_roster.json"
    roster_path.write_text(
        json.dumps(
            {
                "version": 1,
                "primary": {
                    "id": "oncall-primary",
                    "webhook_url": "http://oncall.invalid/webhook",
                    "email": ["oncall@example.local"],
                },
            }
        ),
        encoding="utf-8",
    )
    out_path = tmp_path / "incident_notify.json"
    seen: dict[str, object] = {}

    def _fake_notify_once(**kwargs):  # type: ignore[no-untyped-def]
        seen["webhook_url"] = kwargs.get("webhook_url")
        return ([{"channel": "webhook", "ok": True, "status": "http_200", "attempts": []}], ["webhook"])

    monkeypatch.setattr(incident_notify, "_notify_once", _fake_notify_once)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "incident_notify.py",
            "--incident-report",
            incident_path.as_posix(),
            "--webhook-url",
            "http://default.invalid/webhook",
            "--oncall-roster",
            roster_path.as_posix(),
            "--out",
            out_path.as_posix(),
        ],
    )
    code = incident_notify.main()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 0
    assert data["ok"] is True
    assert data["oncall_roster"]["loaded"] is True
    assert data["oncall_roster"]["used"] is True
    assert seen["webhook_url"] == "http://oncall.invalid/webhook"


def test_main_can_disable_oncall_roster_preference(monkeypatch, tmp_path: Path) -> None:
    incident_path = tmp_path / "incident_report_1.json"
    incident_path.write_text(
        json.dumps({"incident": {"incident_id": "INC-ONCALL-2", "severity": "critical", "escalation_level": "p1"}}),
        encoding="utf-8",
    )
    roster_path = tmp_path / "oncall_roster.json"
    roster_path.write_text(
        json.dumps(
            {
                "version": 1,
                "primary": {
                    "id": "oncall-primary",
                    "webhook_url": "http://oncall.invalid/webhook",
                    "email": ["oncall@example.local"],
                },
            }
        ),
        encoding="utf-8",
    )
    out_path = tmp_path / "incident_notify.json"
    seen: dict[str, object] = {}

    def _fake_notify_once(**kwargs):  # type: ignore[no-untyped-def]
        seen["webhook_url"] = kwargs.get("webhook_url")
        return ([{"channel": "webhook", "ok": True, "status": "http_200", "attempts": []}], ["webhook"])

    monkeypatch.setattr(incident_notify, "_notify_once", _fake_notify_once)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "incident_notify.py",
            "--incident-report",
            incident_path.as_posix(),
            "--webhook-url",
            "http://default.invalid/webhook",
            "--oncall-roster",
            roster_path.as_posix(),
            "--prefer-oncall-roster",
            "0",
            "--out",
            out_path.as_posix(),
        ],
    )
    code = incident_notify.main()
    data = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 0
    assert data["ok"] is True
    assert data["oncall_roster"]["loaded"] is True
    assert data["oncall_roster"]["used"] is False
    assert seen["webhook_url"] == "http://default.invalid/webhook"
