from __future__ import annotations

import json
import sys
from pathlib import Path

from scripts import sensitive_output_scan


def test_mask_keeps_partial_shape() -> None:
    masked = sensitive_output_scan._mask("sk-supersecrettoken123456")
    assert masked.startswith("sk-")
    assert masked.endswith("56")
    assert "***" in masked


def test_scan_text_detects_token() -> None:
    findings = sensitive_output_scan._scan_text(
        "api_key=sk-supersecrettoken123456",
        path=Path("sample.log"),
        max_findings=10,
    )
    assert len(findings) >= 1
    rule_ids = {str(row.get("rule_id") or "") for row in findings}
    assert "openai_key" in rule_ids
    assert all("supersecrettoken" not in str(row.get("masked_match") or "") for row in findings)


def test_main_fails_when_findings_over_threshold(monkeypatch, tmp_path: Path) -> None:
    data = tmp_path / "artifact.log"
    data.write_text("Authorization: Bearer sk-supersecrettoken123456", encoding="utf-8")
    out_path = tmp_path / "scan.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "sensitive_output_scan.py",
            "--path-glob",
            data.as_posix(),
            "--max-findings",
            "0",
            "--strict",
            "--out",
            out_path.as_posix(),
        ],
    )
    code = sensitive_output_scan.main()
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 2
    assert report["ok"] is False
    assert len(report["findings"]) >= 1


def test_main_passes_when_threshold_allows(monkeypatch, tmp_path: Path) -> None:
    data = tmp_path / "artifact.log"
    data.write_text("token=abcdefghi123456789", encoding="utf-8")
    out_path = tmp_path / "scan.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "sensitive_output_scan.py",
            "--path-glob",
            data.as_posix(),
            "--max-findings",
            "1",
            "--out",
            out_path.as_posix(),
        ],
    )
    code = sensitive_output_scan.main()
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 0
    assert report["ok"] is True
