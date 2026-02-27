from __future__ import annotations

import json
import sys
from pathlib import Path

from scripts import migration_assistant


def test_migration_assistant_strict_success(monkeypatch, tmp_path: Path) -> None:
    init_file = tmp_path / "__init__.py"
    init_file.write_text('__version__ = "0.1.0"\n', encoding="utf-8")
    matrix = tmp_path / "matrix.json"
    matrix.write_text(
        json.dumps(
            {
                "version": 1,
                "cases": [
                    {"direction": "upgrade", "from_version": "0.0.9", "to_version": "0.1.0"},
                    {"direction": "rollback", "from_version": "0.2.0", "to_version": "0.1.0"},
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    policy = tmp_path / "policy.json"
    policy.write_text(
        json.dumps({"version": 1, "state_schema": {"current": "2.1"}}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    out_path = tmp_path / "migration_assistant.json"
    out_md = tmp_path / "migration_assistant.md"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "migration_assistant.py",
            "--init-file",
            init_file.as_posix(),
            "--matrix",
            matrix.as_posix(),
            "--policy",
            policy.as_posix(),
            "--from-version",
            "0.0.9",
            "--to-version",
            "0.1.0",
            "--strict",
            "--out",
            out_path.as_posix(),
            "--out-md",
            out_md.as_posix(),
        ],
    )
    code = migration_assistant.main()
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 0
    assert report["ok"] is True
    assert out_md.exists()


def test_migration_assistant_strict_fails_without_rollback_path(monkeypatch, tmp_path: Path) -> None:
    init_file = tmp_path / "__init__.py"
    init_file.write_text('__version__ = "0.1.0"\n', encoding="utf-8")
    matrix = tmp_path / "matrix.json"
    matrix.write_text(
        json.dumps(
            {
                "version": 1,
                "cases": [
                    {"direction": "upgrade", "from_version": "0.0.9", "to_version": "0.1.0"},
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    policy = tmp_path / "policy.json"
    policy.write_text(
        json.dumps({"version": 1, "state_schema": {"current": "2.1"}}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    out_path = tmp_path / "migration_assistant.json"
    out_md = tmp_path / "migration_assistant.md"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "migration_assistant.py",
            "--init-file",
            init_file.as_posix(),
            "--matrix",
            matrix.as_posix(),
            "--policy",
            policy.as_posix(),
            "--from-version",
            "0.0.9",
            "--to-version",
            "0.1.0",
            "--strict",
            "--out",
            out_path.as_posix(),
            "--out-md",
            out_md.as_posix(),
        ],
    )
    code = migration_assistant.main()
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 2
    assert report["ok"] is False
