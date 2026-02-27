from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from scripts import capacity_stress_gate


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_gate_strict_passes_with_fresh_report(monkeypatch, tmp_path: Path) -> None:
    now = time.time()
    report = tmp_path / "stress.json"
    out_path = tmp_path / "gate.json"
    _write_json(
        report,
        {
            "ok": True,
            "ended_at": now - 120.0,
            "summary": {"profiles_total": 3, "profiles_fail": 0},
            "soak": {"ok": True, "report_ok": True},
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "capacity_stress_gate.py",
            "--report",
            report.as_posix(),
            "--max-age-s",
            "3600",
            "--min-profiles",
            "3",
            "--max-failed-profiles",
            "0",
            "--require-soak",
            "--strict",
            "--out",
            out_path.as_posix(),
        ],
    )
    code = capacity_stress_gate.main()
    body = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 0
    assert body["ok"] is True


def test_gate_strict_fails_when_report_is_stale(monkeypatch, tmp_path: Path) -> None:
    now = time.time()
    report = tmp_path / "stress.json"
    out_path = tmp_path / "gate.json"
    _write_json(
        report,
        {
            "ok": True,
            "ended_at": now - 86400.0,
            "summary": {"profiles_total": 3, "profiles_fail": 0},
            "soak": {"ok": True, "report_ok": True},
        },
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "capacity_stress_gate.py",
            "--report",
            report.as_posix(),
            "--max-age-s",
            "300",
            "--strict",
            "--out",
            out_path.as_posix(),
        ],
    )
    code = capacity_stress_gate.main()
    body = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 2
    assert body["ok"] is False


def test_gate_non_strict_returns_zero_when_missing_report(monkeypatch, tmp_path: Path) -> None:
    out_path = tmp_path / "gate.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "capacity_stress_gate.py",
            "--report",
            (tmp_path / "missing.json").as_posix(),
            "--out",
            out_path.as_posix(),
        ],
    )
    code = capacity_stress_gate.main()
    body = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 0
    assert body["ok"] is False
