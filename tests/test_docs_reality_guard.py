from __future__ import annotations

import json
import sys
from pathlib import Path

from scripts import docs_reality_guard


def _write_policy(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "doc_globs": ["docs/**/*.md"],
                "path_prefixes": ["docs/", "scripts/", "security/"],
                "max_missing_paths": 0,
                "max_command_failures": 0,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def test_docs_reality_guard_passes_with_existing_paths_and_callable_commands(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "scripts").mkdir(parents=True, exist_ok=True)
    _write_policy(tmp_path / "security" / "docs_reality_policy.json")
    (tmp_path / "scripts" / "demo.py").write_text(
        "\n".join(
            [
                "import argparse",
                "parser = argparse.ArgumentParser()",
                "parser.add_argument('--quick', action='store_true')",
                "parser.parse_args()",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "docs" / "guide.md").write_text(
        "\n".join(
            [
                "# Guide",
                "Use `scripts/demo.py` to run local diagnostics.",
                "```powershell",
                "python scripts/demo.py --quick",
                "```",
            ]
        ),
        encoding="utf-8",
    )

    out_path = tmp_path / "report.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "docs_reality_guard.py",
            "--policy",
            "security/docs_reality_policy.json",
            "--require-python-command-check",
            "--strict",
            "--out",
            out_path.as_posix(),
        ],
    )
    code = docs_reality_guard.main()
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 0
    assert report["ok"] is True
    assert report["missing_paths"] == []
    path_row = [row for row in report["checks"] if row["id"] == "doc_referenced_paths_exist"][0]
    assert path_row["ok"] is True
    cmd_row = [row for row in report["checks"] if row["id"] == "doc_python_commands_callable"][0]
    assert cmd_row["ok"] is True


def test_docs_reality_guard_fails_when_referenced_path_missing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    _write_policy(tmp_path / "security" / "docs_reality_policy.json")
    (tmp_path / "docs" / "guide.md").write_text(
        "\n".join(
            [
                "# Missing",
                "This command references `scripts/not_found.py` and should fail.",
            ]
        ),
        encoding="utf-8",
    )

    out_path = tmp_path / "report.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "docs_reality_guard.py",
            "--policy",
            "security/docs_reality_policy.json",
            "--strict",
            "--out",
            out_path.as_posix(),
        ],
    )
    code = docs_reality_guard.main()
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 2
    assert report["ok"] is False
    assert "scripts/not_found.py" in report["missing_paths"]
    path_row = [row for row in report["checks"] if row["id"] == "doc_referenced_paths_exist"][0]
    assert path_row["ok"] is False


def test_docs_reality_guard_inline_command_path_uses_script_token(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    (tmp_path / "scripts").mkdir(parents=True, exist_ok=True)
    _write_policy(tmp_path / "security" / "docs_reality_policy.json")
    (tmp_path / "scripts" / "demo.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "docs" / "guide.md").write_text(
        "Use `scripts/demo.py --quick` during local checks.\n",
        encoding="utf-8",
    )

    out_path = tmp_path / "report.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "docs_reality_guard.py",
            "--policy",
            "security/docs_reality_policy.json",
            "--strict",
            "--out",
            out_path.as_posix(),
        ],
    )
    code = docs_reality_guard.main()
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 0
    assert report["ok"] is True
    assert report["missing_paths"] == []


def test_docs_reality_guard_fails_when_python_command_not_callable(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    _write_policy(tmp_path / "security" / "docs_reality_policy.json")
    (tmp_path / "docs" / "guide.md").write_text(
        "\n".join(
            [
                "# Commands",
                "```powershell",
                "python scripts/does_not_exist.py --quick",
                "```",
            ]
        ),
        encoding="utf-8",
    )

    out_path = tmp_path / "report.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "docs_reality_guard.py",
            "--policy",
            "security/docs_reality_policy.json",
            "--require-python-command-check",
            "--strict",
            "--out",
            out_path.as_posix(),
        ],
    )
    code = docs_reality_guard.main()
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 2
    assert report["ok"] is False
    assert len(report["command_failures"]) == 1
    assert report["command_failures"][0]["check_reason"] == "script_missing"
    cmd_row = [row for row in report["checks"] if row["id"] == "doc_python_commands_callable"][0]
    assert cmd_row["ok"] is False


def test_docs_reality_guard_checks_python_script_without_args(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "docs").mkdir(parents=True, exist_ok=True)
    _write_policy(tmp_path / "security" / "docs_reality_policy.json")
    (tmp_path / "docs" / "guide.md").write_text(
        "\n".join(
            [
                "# Commands",
                "```powershell",
                "python scripts/does_not_exist.py",
                "```",
            ]
        ),
        encoding="utf-8",
    )

    out_path = tmp_path / "report.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "docs_reality_guard.py",
            "--policy",
            "security/docs_reality_policy.json",
            "--require-python-command-check",
            "--strict",
            "--out",
            out_path.as_posix(),
        ],
    )
    code = docs_reality_guard.main()
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 2
    assert report["ok"] is False
    assert len(report["command_failures"]) == 1
    assert report["command_failures"][0]["check_reason"] == "script_missing"
