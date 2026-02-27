from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from scripts import sign_rollback_drill_evidence


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_sign_rollback_drill_evidence_strict_passes_with_key(monkeypatch, tmp_path: Path) -> None:
    now = time.time()
    incident = tmp_path / "incident_notify_drill_1.json"
    rollback = tmp_path / "rollback_bundle_report_1.json"
    _write_json(incident, {"ok": True, "ended_at": now - 20})
    _write_json(rollback, {"ok": True, "generated_at": now - 10, "missing_required": []})

    out = tmp_path / "signature_report.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "sign_rollback_drill_evidence.py",
            "--incident-drill-pattern",
            (tmp_path / "incident_notify_drill_*.json").as_posix(),
            "--rollback-bundle-pattern",
            (tmp_path / "rollback_bundle_report_*.json").as_posix(),
            "--require-key",
            "--signing-key",
            "secret-key",
            "--strict",
            "--out",
            out.as_posix(),
        ],
    )
    code = sign_rollback_drill_evidence.main()
    body = json.loads(out.read_text(encoding="utf-8"))
    assert code == 0
    assert body["ok"] is True
    assert isinstance(body.get("signature"), str) and body["signature"]


def test_sign_rollback_drill_evidence_strict_fails_when_key_missing(monkeypatch, tmp_path: Path) -> None:
    now = time.time()
    incident = tmp_path / "incident_notify_drill_1.json"
    rollback = tmp_path / "rollback_bundle_report_1.json"
    _write_json(incident, {"ok": True, "ended_at": now - 20})
    _write_json(rollback, {"ok": True, "generated_at": now - 10, "missing_required": []})

    out = tmp_path / "signature_report.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "sign_rollback_drill_evidence.py",
            "--incident-drill-pattern",
            (tmp_path / "incident_notify_drill_*.json").as_posix(),
            "--rollback-bundle-pattern",
            (tmp_path / "rollback_bundle_report_*.json").as_posix(),
            "--require-key",
            "--strict",
            "--out",
            out.as_posix(),
        ],
    )
    code = sign_rollback_drill_evidence.main()
    body = json.loads(out.read_text(encoding="utf-8"))
    assert code == 2
    assert body["ok"] is False
