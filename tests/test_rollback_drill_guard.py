from __future__ import annotations

import hashlib
import hmac
import json
import sys
import time
from pathlib import Path

from scripts import rollback_drill_guard


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_rollback_drill_guard_strict_passes_with_fresh_evidence(monkeypatch, tmp_path: Path) -> None:
    now = time.time()
    incident = tmp_path / "incident_notify_drill_1.json"
    rollback = tmp_path / "rollback_bundle_report_1.json"
    channels = tmp_path / "release_channels.json"
    out_path = tmp_path / "rollback_drill_guard.json"

    _write_json(
        incident,
        {
            "ok": True,
            "with_email": True,
            "started_at": now - 80,
            "ended_at": now - 60,
        },
    )
    _write_json(
        rollback,
        {
            "ok": True,
            "generated_at": now - 40,
            "missing_required": [],
        },
    )
    _write_json(
        channels,
        {
            "version": 1,
            "updated_at": now,
            "channels": {
                "canary": {"version": "0.1.0", "rollout_percent": 5, "updated_at": now},
                "stable": {"version": "0.1.0", "rollout_percent": 100, "updated_at": now},
            },
            "history": [
                {
                    "ts": now - 120,
                    "action": "rollback",
                    "channel": "stable",
                    "from_version": "0.1.1",
                    "to_version": "0.1.0",
                    "reason": "rollback drill rehearsal",
                    "actor": "release-bot",
                }
            ],
        },
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "rollback_drill_guard.py",
            "--incident-drill-pattern",
            (tmp_path / "incident_notify_drill_*.json").as_posix(),
            "--rollback-bundle-pattern",
            (tmp_path / "rollback_bundle_report_*.json").as_posix(),
            "--channels-file",
            channels.as_posix(),
            "--require-email-drill",
            "--require-history-rollback",
            "--strict",
            "--out",
            out_path.as_posix(),
        ],
    )
    code = rollback_drill_guard.main()
    body = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 0
    assert body["ok"] is True


def test_rollback_drill_guard_strict_fails_when_incident_drill_missing(monkeypatch, tmp_path: Path) -> None:
    now = time.time()
    rollback = tmp_path / "rollback_bundle_report_1.json"
    out_path = tmp_path / "rollback_drill_guard.json"

    _write_json(
        rollback,
        {
            "ok": True,
            "generated_at": now - 40,
            "missing_required": [],
        },
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "rollback_drill_guard.py",
            "--incident-drill-pattern",
            (tmp_path / "incident_notify_drill_*.json").as_posix(),
            "--rollback-bundle-pattern",
            (tmp_path / "rollback_bundle_report_*.json").as_posix(),
            "--strict",
            "--out",
            out_path.as_posix(),
        ],
    )
    code = rollback_drill_guard.main()
    body = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 2
    assert body["ok"] is False
    assert any(row["id"] == "incident_drill_reports_count" and row["ok"] is False for row in body["checks"])


def test_rollback_drill_guard_non_strict_returns_zero_on_missing_evidence(monkeypatch, tmp_path: Path) -> None:
    out_path = tmp_path / "rollback_drill_guard.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "rollback_drill_guard.py",
            "--incident-drill-pattern",
            (tmp_path / "incident_notify_drill_*.json").as_posix(),
            "--rollback-bundle-pattern",
            (tmp_path / "rollback_bundle_report_*.json").as_posix(),
            "--out",
            out_path.as_posix(),
        ],
    )
    code = rollback_drill_guard.main()
    body = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 0
    assert body["ok"] is False


def test_rollback_drill_guard_strict_signature_requirement(monkeypatch, tmp_path: Path) -> None:
    now = time.time()
    incident = tmp_path / "incident_notify_drill_1.json"
    rollback = tmp_path / "rollback_bundle_report_1.json"
    signature = tmp_path / "rollback_drill_signature_1.json"
    channels = tmp_path / "release_channels.json"
    policy = tmp_path / "rollback_drill_signature_policy.json"
    out_path = tmp_path / "rollback_drill_guard.json"

    _write_json(
        incident,
        {
            "ok": True,
            "with_email": True,
            "started_at": now - 80,
            "ended_at": now - 60,
        },
    )
    _write_json(
        rollback,
        {
            "ok": True,
            "generated_at": now - 40,
            "missing_required": [],
        },
    )
    _write_json(
        channels,
        {
            "version": 1,
            "updated_at": now,
            "channels": {"stable": {"version": "0.1.0", "rollout_percent": 100, "updated_at": now}},
            "history": [],
        },
    )
    _write_json(
        policy,
        {
            "version": 1,
            "required": True,
            "required_in_strict": True,
            "require_signing_key": True,
            "max_signature_age_s": 3000,
        },
    )

    payload = {
        "version": 1,
        "signed_at": now - 20,
        "algorithm": "hmac-sha256",
        "key_id": "test",
        "artifacts": [
            {
                "path": incident.as_posix(),
                "size": int(incident.stat().st_size),
                "mtime": round(float(incident.stat().st_mtime), 3),
                "sha256": hashlib.sha256(incident.read_bytes()).hexdigest(),
            },
            {
                "path": rollback.as_posix(),
                "size": int(rollback.stat().st_size),
                "mtime": round(float(rollback.stat().st_mtime), 3),
                "sha256": hashlib.sha256(rollback.read_bytes()).hexdigest(),
            },
        ],
    }
    payload_text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hmac.new(b"secret-sign-key", payload_text.encode("utf-8"), hashlib.sha256).hexdigest()
    _write_json(
        signature,
        {
            "ok": True,
            "signed_at": payload["signed_at"],
            "payload": payload,
            "signature": digest,
        },
    )

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "rollback_drill_guard.py",
            "--incident-drill-pattern",
            (tmp_path / "incident_notify_drill_*.json").as_posix(),
            "--rollback-bundle-pattern",
            (tmp_path / "rollback_bundle_report_*.json").as_posix(),
            "--signature-pattern",
            (tmp_path / "rollback_drill_signature_*.json").as_posix(),
            "--signature-policy",
            policy.as_posix(),
            "--signing-key",
            "secret-sign-key",
            "--strict",
            "--out",
            out_path.as_posix(),
        ],
    )
    code = rollback_drill_guard.main()
    body = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 0
    assert body["ok"] is True
    assert any(row["id"] == "rollback_signature_reports_valid" and row["ok"] is True for row in body["checks"])
