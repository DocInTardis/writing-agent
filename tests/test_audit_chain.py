from __future__ import annotations

import json
import sys
from pathlib import Path

from scripts import audit_chain, verify_audit_chain


def test_append_and_verify_chain_roundtrip(tmp_path: Path) -> None:
    log_path = tmp_path / "audit.ndjson"
    state_path = tmp_path / "audit_state.json"

    first = audit_chain.record_operation(
        action="release_rollout_execute",
        actor="release-bot",
        source="unit-test",
        status="ok",
        context={"target_version": "1.2.3"},
        log_path=log_path,
        state_path=state_path,
        strict=True,
    )
    second = audit_chain.record_operation(
        action="incident_notify",
        actor="incident-bot",
        source="unit-test",
        status="ok",
        context={"incident_id": "inc-1"},
        log_path=log_path,
        state_path=state_path,
        strict=True,
    )

    assert first["ok"] is True
    assert second["ok"] is True
    state = audit_chain.load_state(state_path)
    verified = audit_chain.verify_chain(
        log_path=log_path,
        state=state,
        require_log=True,
        strict=True,
    )
    assert verified["ok"] is True
    assert int(verified["entry_count"]) == 2


def test_verify_chain_detects_tampered_entry_hash(tmp_path: Path) -> None:
    log_path = tmp_path / "audit.ndjson"
    state_path = tmp_path / "audit_state.json"
    audit_chain.record_operation(
        action="release_channel_set",
        actor="release-bot",
        source="unit-test",
        status="ok",
        context={"channel": "canary", "version": "1.2.3"},
        log_path=log_path,
        state_path=state_path,
        strict=True,
    )
    audit_chain.record_operation(
        action="release_channel_promote",
        actor="release-bot",
        source="unit-test",
        status="ok",
        context={"source": "canary", "target": "stable"},
        log_path=log_path,
        state_path=state_path,
        strict=True,
    )

    lines = [line for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    first = json.loads(lines[0])
    first["action"] = "tampered_action"
    lines[0] = json.dumps(first, ensure_ascii=False, sort_keys=True)
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    verified = audit_chain.verify_chain(
        log_path=log_path,
        state=audit_chain.load_state(state_path),
        require_log=True,
        strict=True,
    )
    assert verified["ok"] is False
    failed_ids = {str(row.get("id")) for row in verified.get("checks", []) if not bool(row.get("ok"))}
    assert "entry_1_hash_match" in failed_ids


def test_verify_script_returns_non_zero_on_tamper(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "audit.ndjson"
    state_path = tmp_path / "audit_state.json"
    out_path = tmp_path / "verify_report.json"

    audit_chain.record_operation(
        action="rollback_bundle_create",
        actor="release-bot",
        source="unit-test",
        status="ok",
        context={"label": "test"},
        log_path=log_path,
        state_path=state_path,
        strict=True,
    )

    lines = [line for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    tampered = json.loads(lines[0])
    tampered["context"] = {"label": "tampered"}
    lines[0] = json.dumps(tampered, ensure_ascii=False, sort_keys=True)
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "verify_audit_chain.py",
            "--log",
            log_path.as_posix(),
            "--state-file",
            state_path.as_posix(),
            "--require-log",
            "--strict",
            "--out",
            out_path.as_posix(),
        ],
    )
    code = verify_audit_chain.main()
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 2
    assert report["ok"] is False
