from __future__ import annotations

import json
import sys
from pathlib import Path

from scripts import doc_encoding_guard


def test_doc_encoding_guard_strict_passes_for_clean_docs(monkeypatch, tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    (docs_dir / "a.md").write_text("# Clean\n\nAll good.\n", encoding="utf-8")
    (docs_dir / "b.md").write_text("# Another\n\nNo mojibake.\n", encoding="utf-8")

    out = tmp_path / "report.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "doc_encoding_guard.py",
            "--docs-root",
            docs_dir.as_posix(),
            "--strict",
            "--out",
            out.as_posix(),
        ],
    )
    code = doc_encoding_guard.main()
    report = json.loads(out.read_text(encoding="utf-8"))
    assert code == 0
    assert report["ok"] is True


def test_doc_encoding_guard_detects_suspicious_mojibake(monkeypatch, tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    bad_text = "鏄鍙鍚鍦鍐鍑鎴闂瑙鏃绗澶锛銆" * 5
    (docs_dir / "bad.md").write_text(bad_text, encoding="utf-8")

    out = tmp_path / "report.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "doc_encoding_guard.py",
            "--docs-root",
            docs_dir.as_posix(),
            "--strict",
            "--min-hint-count",
            "5",
            "--min-hint-ratio",
            "0.01",
            "--out",
            out.as_posix(),
        ],
    )
    code = doc_encoding_guard.main()
    report = json.loads(out.read_text(encoding="utf-8"))
    assert code == 2
    row = [entry for entry in report["checks"] if entry["id"] == "docs_mojibake_suspicious_bound"][0]
    assert row["ok"] is False


def test_doc_encoding_guard_detects_utf8_decode_failure(monkeypatch, tmp_path: Path) -> None:
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    bad_file = docs_dir / "broken.md"
    bad_file.write_bytes(b"\xff\xfe\x00broken")

    out = tmp_path / "report.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "doc_encoding_guard.py",
            "--docs-root",
            docs_dir.as_posix(),
            "--strict",
            "--out",
            out.as_posix(),
        ],
    )
    code = doc_encoding_guard.main()
    report = json.loads(out.read_text(encoding="utf-8"))
    assert code == 2
    row = [entry for entry in report["checks"] if entry["id"] == "docs_utf8_decode"][0]
    assert row["ok"] is False
