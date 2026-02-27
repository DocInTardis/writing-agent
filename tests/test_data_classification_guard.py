from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from scripts import data_classification_guard


def test_data_classification_guard_detects_sensitive_and_retention_violation(monkeypatch, tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "report.json"
    target.write_text('{"token":"sk-supersecrettoken1234567890"}', encoding="utf-8")

    old_ts = time.time() - 3.0 * 86400.0
    os.utime(target, (old_ts, old_ts))

    policy_path = tmp_path / "policy.json"
    policy_path.write_text(
        json.dumps(
            {
                "version": 1,
                "default_max_unmasked_findings": 0,
                "artifact_rules": [
                    {
                        "id": "out_json",
                        "glob": (out_dir / "*.json").as_posix(),
                        "classification": "internal",
                        "max_age_days": 1,
                        "required": True,
                    }
                ],
                "class_limits": {"internal": {"max_unmasked_findings": 0}},
                "sensitive_patterns": [{"id": "openai_key", "regex": r"\bsk-[A-Za-z0-9]{20,}\b"}],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    out_path = tmp_path / "data_classification_guard.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "data_classification_guard.py",
            "--policy",
            policy_path.as_posix(),
            "--strict",
            "--require-rules",
            "--out",
            out_path.as_posix(),
        ],
    )
    code = data_classification_guard.main()
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 2
    assert report["ok"] is False
    assert len(report["findings"]) >= 1
    assert len(report["retention_violations"]) >= 1


def test_data_classification_guard_passes_for_masked_content(monkeypatch, tmp_path: Path) -> None:
    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "report.json"
    target.write_text('{"token":"sk-***56"}', encoding="utf-8")

    policy_path = tmp_path / "policy.json"
    policy_path.write_text(
        json.dumps(
            {
                "version": 1,
                "default_max_unmasked_findings": 0,
                "artifact_rules": [
                    {
                        "id": "out_json",
                        "glob": (out_dir / "*.json").as_posix(),
                        "classification": "internal",
                        "max_age_days": 30,
                        "required": True,
                    }
                ],
                "class_limits": {"internal": {"max_unmasked_findings": 0}},
                "sensitive_patterns": [{"id": "openai_key", "regex": r"\bsk-[A-Za-z0-9]{20,}\b"}],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    out_path = tmp_path / "data_classification_guard.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "data_classification_guard.py",
            "--policy",
            policy_path.as_posix(),
            "--strict",
            "--require-rules",
            "--out",
            out_path.as_posix(),
        ],
    )
    code = data_classification_guard.main()
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 0
    assert report["ok"] is True
    assert len(report["findings"]) == 0
