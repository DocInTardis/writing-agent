from __future__ import annotations

import json
import sys
from pathlib import Path

from scripts import correlation_trace_guard


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_correlation_trace_guard_strict_passes_with_consistent_ids(monkeypatch, tmp_path: Path) -> None:
    rollout = tmp_path / "rollout.json"
    alert = tmp_path / "alert.json"
    incident = tmp_path / "incident.json"
    out_path = tmp_path / "guard.json"
    _write_json(
        rollout,
        {
            "correlation": {"correlation_id": "corr-1", "release_candidate_id": "rc-1"},
        },
    )
    _write_json(
        alert,
        {
            "correlation": {"correlation_id": "corr-1", "release_candidate_id": "rc-1"},
        },
    )
    _write_json(
        incident,
        {
            "incident": {"correlation_id": "corr-1", "release_candidate_id": "rc-1"},
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "correlation_trace_guard.py",
            "--rollout-report",
            rollout.as_posix(),
            "--alert-report",
            alert.as_posix(),
            "--incident-report",
            incident.as_posix(),
            "--strict",
            "--out",
            out_path.as_posix(),
        ],
    )
    code = correlation_trace_guard.main()
    body = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 0
    assert body["ok"] is True


def test_correlation_trace_guard_strict_fails_with_mismatched_ids(monkeypatch, tmp_path: Path) -> None:
    rollout = tmp_path / "rollout.json"
    alert = tmp_path / "alert.json"
    incident = tmp_path / "incident.json"
    out_path = tmp_path / "guard.json"
    _write_json(
        rollout,
        {
            "correlation": {"correlation_id": "corr-1", "release_candidate_id": "rc-1"},
        },
    )
    _write_json(
        alert,
        {
            "correlation": {"correlation_id": "corr-2", "release_candidate_id": "rc-2"},
        },
    )
    _write_json(
        incident,
        {
            "incident": {"correlation_id": "corr-1", "release_candidate_id": "rc-1"},
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "correlation_trace_guard.py",
            "--rollout-report",
            rollout.as_posix(),
            "--alert-report",
            alert.as_posix(),
            "--incident-report",
            incident.as_posix(),
            "--strict",
            "--out",
            out_path.as_posix(),
        ],
    )
    code = correlation_trace_guard.main()
    body = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 2
    assert body["ok"] is False
