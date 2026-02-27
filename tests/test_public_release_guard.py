from __future__ import annotations

import json
import sys
from pathlib import Path

from scripts import public_release_guard


def test_public_release_guard_strict_success(monkeypatch, tmp_path: Path) -> None:
    init_file = tmp_path / "__init__.py"
    init_file.write_text('__version__ = "1.2.3"\n', encoding="utf-8")
    changes = tmp_path / "CHANGES.md"
    changes.write_text("# Changelog\n\n- item\n", encoding="utf-8")

    must_doc = tmp_path / "docs" / "START_HERE.md"
    must_doc.parent.mkdir(parents=True, exist_ok=True)
    must_doc.write_text("ok", encoding="utf-8")
    must_wf = tmp_path / ".github" / "workflows" / "public-release.yml"
    must_wf.parent.mkdir(parents=True, exist_ok=True)
    must_wf.write_text("name: x", encoding="utf-8")
    must_script = tmp_path / "scripts" / "migration_assistant.py"
    must_script.parent.mkdir(parents=True, exist_ok=True)
    must_script.write_text("# stub", encoding="utf-8")

    policy = tmp_path / "policy.json"
    policy.write_text(
        json.dumps(
            {
                "version": 1,
                "required_docs": [must_doc.as_posix()],
                "required_workflows": [must_wf.as_posix()],
                "required_scripts": [must_script.as_posix()],
                "release_notes": {"required": True},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    notes_out = tmp_path / "release_notes.md"
    out_path = tmp_path / "public_release_guard.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "public_release_guard.py",
            "--policy",
            policy.as_posix(),
            "--init-file",
            init_file.as_posix(),
            "--changes-file",
            changes.as_posix(),
            "--release-version",
            "1.2.3",
            "--release-notes-out",
            notes_out.as_posix(),
            "--strict",
            "--out",
            out_path.as_posix(),
        ],
    )
    code = public_release_guard.main()
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 0
    assert report["ok"] is True
    assert notes_out.exists()


def test_public_release_guard_fails_on_version_mismatch(monkeypatch, tmp_path: Path) -> None:
    init_file = tmp_path / "__init__.py"
    init_file.write_text('__version__ = "1.2.3"\n', encoding="utf-8")
    changes = tmp_path / "CHANGES.md"
    changes.write_text("# Changelog\n", encoding="utf-8")

    policy = tmp_path / "policy.json"
    policy.write_text(
        json.dumps(
            {
                "version": 1,
                "required_docs": [],
                "required_workflows": [],
                "required_scripts": [],
                "release_notes": {"required": False},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    out_path = tmp_path / "public_release_guard.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "public_release_guard.py",
            "--policy",
            policy.as_posix(),
            "--init-file",
            init_file.as_posix(),
            "--changes-file",
            changes.as_posix(),
            "--release-version",
            "2.0.0",
            "--strict",
            "--out",
            out_path.as_posix(),
        ],
    )
    code = public_release_guard.main()
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 2
    assert report["ok"] is False
