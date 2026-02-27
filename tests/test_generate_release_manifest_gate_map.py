from __future__ import annotations

import json
from pathlib import Path

from scripts import generate_release_manifest


def test_derive_release_candidate_id_prefers_explicit_value() -> None:
    out = generate_release_manifest._derive_release_candidate_id(
        release_candidate_id="rc-custom",
        app_version="1.2.3",
        git_commit="abcdef123456",
        generated_at_ts=1700000000,
    )
    assert out == "rc-custom"


def test_derive_release_candidate_id_falls_back_to_version_and_commit() -> None:
    out = generate_release_manifest._derive_release_candidate_id(
        release_candidate_id="",
        app_version="1.2.3",
        git_commit="abcdef1234567890",
        generated_at_ts=1700000000,
    )
    assert out == "rc-1.2.3-abcdef123456"


def test_build_gate_evidence_map_collects_latest_artifacts(tmp_path: Path, monkeypatch) -> None:
    out_dir = tmp_path / ".data/out"
    out_dir.mkdir(parents=True, exist_ok=True)
    a = out_dir / "release_governance_1.json"
    b = out_dir / "release_governance_2.json"
    a.write_text(json.dumps({"ok": True, "ended_at": 100.0}), encoding="utf-8")
    b.write_text(json.dumps({"ok": True, "ended_at": 120.0}), encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    payload, missing = generate_release_manifest._build_gate_evidence_map(
        release_candidate_id="rc-test",
        patterns=[".data/out/release_governance_*.json"],
        recent=1,
    )
    assert payload["release_candidate_id"] == "rc-test"
    assert isinstance(payload["evidence_sha256"], str) and payload["evidence_sha256"]
    rows = payload["evidence"]["release_governance"]["rows"]
    assert len(rows) == 1
    assert rows[0]["path"].endswith("release_governance_2.json")
    assert missing == []
