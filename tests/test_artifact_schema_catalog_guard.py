from __future__ import annotations

import json
import sys
from pathlib import Path

from scripts import artifact_schema_catalog_guard


def test_artifact_schema_catalog_guard_strict_pass(monkeypatch, tmp_path: Path) -> None:
    evidence = tmp_path / "release_preflight_1.json"
    evidence.write_text(
        json.dumps({"ok": True, "started_at": 1.0, "ended_at": 2.0, "steps": []}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    policy = tmp_path / "policy.json"
    policy.write_text(
        json.dumps(
            {
                "version": 1,
                "entries": [
                    {
                        "id": "release_preflight",
                        "artifact_glob": (tmp_path / "release_preflight_*.json").as_posix(),
                        "required_fields": ["ok", "started_at", "ended_at", "steps"],
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    catalog = tmp_path / "catalog.md"
    catalog.write_text(
        "\n".join(
            [
                "# Artifact Schema Catalog",
                "release_preflight",
                f"`{(tmp_path / 'release_preflight_*.json').as_posix()}`",
                "`ok` `started_at` `ended_at` `steps`",
            ]
        ),
        encoding="utf-8",
    )

    out_path = tmp_path / "catalog_guard.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "artifact_schema_catalog_guard.py",
            "--policy",
            policy.as_posix(),
            "--catalog",
            catalog.as_posix(),
            "--strict",
            "--require-evidence",
            "--out",
            out_path.as_posix(),
        ],
    )
    code = artifact_schema_catalog_guard.main()
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 0
    assert report["ok"] is True


def test_artifact_schema_catalog_guard_fails_when_field_missing(monkeypatch, tmp_path: Path) -> None:
    evidence = tmp_path / "release_preflight_1.json"
    evidence.write_text(
        json.dumps({"ok": True, "started_at": 1.0, "ended_at": 2.0}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    policy = tmp_path / "policy.json"
    policy.write_text(
        json.dumps(
            {
                "version": 1,
                "entries": [
                    {
                        "id": "release_preflight",
                        "artifact_glob": (tmp_path / "release_preflight_*.json").as_posix(),
                        "required_fields": ["ok", "started_at", "ended_at", "steps"],
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    catalog = tmp_path / "catalog.md"
    catalog.write_text(
        "\n".join(
            [
                "# Artifact Schema Catalog",
                "release_preflight",
                f"`{(tmp_path / 'release_preflight_*.json').as_posix()}`",
                "`ok` `started_at` `ended_at` `steps`",
            ]
        ),
        encoding="utf-8",
    )

    out_path = tmp_path / "catalog_guard.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "artifact_schema_catalog_guard.py",
            "--policy",
            policy.as_posix(),
            "--catalog",
            catalog.as_posix(),
            "--strict",
            "--require-evidence",
            "--out",
            out_path.as_posix(),
        ],
    )
    code = artifact_schema_catalog_guard.main()
    report = json.loads(out_path.read_text(encoding="utf-8"))
    assert code == 2
    assert report["ok"] is False
