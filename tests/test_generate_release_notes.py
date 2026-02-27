from __future__ import annotations

import json
import sys
from pathlib import Path

from scripts import generate_release_notes


def test_generate_release_notes_success(monkeypatch, tmp_path: Path) -> None:
    changes = tmp_path / "CHANGES.md"
    changes.write_text("# Changelog\n\n## v1.2.3\n- fix A\n- fix B\n", encoding="utf-8")
    out_path = tmp_path / "release_notes.md"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_release_notes.py",
            "--release-version",
            "1.2.3",
            "--changes-file",
            changes.as_posix(),
            "--out",
            out_path.as_posix(),
        ],
    )
    code = generate_release_notes.main()
    assert code == 0
    assert out_path.exists()
    text = out_path.read_text(encoding="utf-8")
    assert "Release 1.2.3" in text


def test_generate_release_notes_invalid_version(monkeypatch, tmp_path: Path) -> None:
    changes = tmp_path / "CHANGES.md"
    changes.write_text("x", encoding="utf-8")
    out_path = tmp_path / "release_notes.md"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "generate_release_notes.py",
            "--release-version",
            "v1",
            "--changes-file",
            changes.as_posix(),
            "--out",
            out_path.as_posix(),
        ],
    )
    code = generate_release_notes.main()
    assert code == 2
