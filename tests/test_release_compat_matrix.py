from __future__ import annotations

import json
import sys
from pathlib import Path

from scripts import release_compat_matrix


def _write_json(path: Path, payload: dict | list) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _run_matrix(monkeypatch, *, policy: Path, matrix: Path, out_path: Path, strict: bool = True) -> tuple[int, dict]:
    argv = [
        "release_compat_matrix.py",
        "--policy",
        policy.as_posix(),
        "--matrix",
        matrix.as_posix(),
        "--out",
        out_path.as_posix(),
    ]
    if strict:
        argv.append("--strict")
    monkeypatch.setattr(sys, "argv", argv)
    code = release_compat_matrix.main()
    body = json.loads(out_path.read_text(encoding="utf-8"))
    return code, body


def test_normalize_state_payload_keeps_required_fields() -> None:
    payload = {"schema_version": "2.1", "state": "S02_DOC_READY", "state_rev": "3"}
    out = release_compat_matrix._normalize_state_payload(payload, target_schema="2.1")
    assert out["schema_version"] == "2.1"
    assert out["state"] == "S02_DOC_READY"
    assert isinstance(out["state_rev"], int)
    for key in ["trace_id", "session_id", "doc_id", "request_id", "created_at", "updated_at"]:
        assert key in out


def test_release_compat_matrix_strict_passes(monkeypatch, tmp_path: Path) -> None:
    fixture_current = tmp_path / "state_context_2_1.json"
    fixture_prev = tmp_path / "state_context_2_0.json"
    fixture_next = tmp_path / "state_context_2_2.json"
    fixture_malformed = tmp_path / "state_context_malformed.json"
    policy = tmp_path / "release_policy.json"
    matrix = tmp_path / "release_compat_matrix.json"
    out_path = tmp_path / "release_compat_matrix_report.json"

    _write_json(
        fixture_current,
        {
            "schema_version": "2.1",
            "trace_id": "x",
            "session_id": "s",
            "doc_id": "d",
            "request_id": "r",
            "state": "S02_DOC_READY",
            "state_rev": 1,
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:01+00:00",
        },
    )
    _write_json(
        fixture_prev,
        {
            "schema_version": "2.0",
            "trace_id": "x-prev",
            "session_id": "s-prev",
            "doc_id": "d-prev",
            "request_id": "r-prev",
            "state": "S02_DOC_READY",
            "state_rev": 1,
            "created_at": "2025-12-31T23:59:00+00:00",
            "updated_at": "2025-12-31T23:59:01+00:00",
        },
    )
    _write_json(
        fixture_next,
        {
            "schema_version": "2.2",
            "trace_id": "x-next",
            "session_id": "s-next",
            "doc_id": "d-next",
            "request_id": "r-next",
            "state": "S02_DOC_READY",
            "state_rev": 2,
            "created_at": "2026-01-02T00:00:00+00:00",
            "updated_at": "2026-01-02T00:00:01+00:00",
        },
    )
    _write_json(fixture_malformed, [{"invalid": True}])

    _write_json(
        policy,
        {
            "version": 1,
            "app_version": "0.1.0",
            "state_schema": {"current": "2.1", "backward_read_compatible": ["2.0", "2.1"]},
            "runtime_data": {
                "files": [
                    {"path": (tmp_path / "runtime_obj.json").as_posix(), "kind": "json_object", "required": False}
                ]
            },
        },
    )
    _write_json(
        matrix,
        {
            "version": 1,
            "cases": [
                {
                    "id": "upgrade_n_minus_one_to_current",
                    "direction": "upgrade",
                    "from_version": "0.0.9",
                    "to_version": "0.1.0",
                    "from_schema": "2.0",
                    "to_schema": "2.1",
                    "state_fixture": fixture_prev.as_posix(),
                    "expect_readable": True,
                },
                {
                    "id": "upgrade_current_to_current",
                    "direction": "upgrade",
                    "from_version": "0.1.0",
                    "to_version": "0.1.0",
                    "from_schema": "2.1",
                    "to_schema": "2.1",
                    "state_fixture": fixture_current.as_posix(),
                    "expect_readable": True,
                },
                {
                    "id": "upgrade_current_to_n_plus_one",
                    "direction": "upgrade",
                    "from_version": "0.1.0",
                    "to_version": "0.2.0",
                    "from_schema": "2.1",
                    "to_schema": "2.2",
                    "state_fixture": fixture_current.as_posix(),
                    "expect_readable": True,
                },
                {
                    "id": "rollback_n_plus_one_to_current",
                    "direction": "rollback",
                    "from_version": "0.2.0",
                    "to_version": "0.1.0",
                    "from_schema": "2.2",
                    "to_schema": "2.1",
                    "allow_forward_schema_source": True,
                    "state_fixture": fixture_next.as_posix(),
                    "expect_readable": True,
                },
                {
                    "id": "rollback_n_plus_one_malformed_fixture",
                    "direction": "rollback",
                    "from_version": "0.2.0",
                    "to_version": "0.1.0",
                    "from_schema": "2.2",
                    "to_schema": "2.1",
                    "state_fixture": fixture_malformed.as_posix(),
                    "expect_readable": False,
                    "expected_failed_checks": ["fixture_loaded", "from_schema_backward_compatible"],
                },
                {
                    "id": "rollback_current_to_current",
                    "direction": "rollback",
                    "from_version": "0.1.0",
                    "to_version": "0.1.0",
                    "from_schema": "2.1",
                    "to_schema": "2.1",
                    "state_fixture": fixture_current.as_posix(),
                    "expect_readable": True,
                },
            ],
            "rules": {
                "require_upgrade_case_for_current_schema": True,
                "require_rollback_case_for_current_schema": True,
                "require_n_minus_one_upgrade_case": True,
                "require_n_plus_one_upgrade_case": True,
                "require_n_plus_one_rollback_case": True,
                "require_failure_mode_case": True,
                "enforce_runtime_contract": True,
            },
        },
    )
    _write_json(tmp_path / "runtime_obj.json", {"ok": 1})

    code, body = _run_matrix(monkeypatch, policy=policy, matrix=matrix, out_path=out_path, strict=True)
    assert code == 0
    assert body["ok"] is True
    checks = {str(row.get("id")): bool(row.get("ok")) for row in body["checks"]}
    assert checks["matrix_covers_n_minus_one_upgrade_case"] is True
    assert checks["matrix_covers_n_plus_one_upgrade_case"] is True
    assert checks["matrix_covers_n_plus_one_rollback_case"] is True
    assert checks["matrix_covers_failure_mode_case"] is True


def test_release_compat_matrix_strict_fails_when_case_fixture_missing(monkeypatch, tmp_path: Path) -> None:
    policy = tmp_path / "release_policy.json"
    matrix = tmp_path / "release_compat_matrix.json"
    out_path = tmp_path / "release_compat_matrix_report.json"
    _write_json(
        policy,
        {
            "version": 1,
            "app_version": "0.1.0",
            "state_schema": {"current": "2.1", "backward_read_compatible": ["2.1"]},
            "runtime_data": {"files": []},
        },
    )
    _write_json(
        matrix,
        {
            "version": 1,
            "cases": [
                {
                    "id": "upgrade",
                    "direction": "upgrade",
                    "from_version": "0.1.0",
                    "to_version": "0.1.0",
                    "from_schema": "2.1",
                    "to_schema": "2.1",
                    "state_fixture": (tmp_path / "missing.json").as_posix(),
                    "expect_readable": True,
                }
            ],
            "rules": {
                "require_upgrade_case_for_current_schema": False,
                "require_rollback_case_for_current_schema": False,
                "require_n_minus_one_upgrade_case": False,
                "require_n_plus_one_upgrade_case": False,
                "require_n_plus_one_rollback_case": False,
                "require_failure_mode_case": False,
                "enforce_runtime_contract": False,
            },
        },
    )

    code, body = _run_matrix(monkeypatch, policy=policy, matrix=matrix, out_path=out_path, strict=True)
    assert code == 2
    assert body["ok"] is False


def test_release_compat_matrix_strict_fails_when_required_n_plus_one_coverage_missing(
    monkeypatch, tmp_path: Path
) -> None:
    fixture = tmp_path / "state_context.json"
    policy = tmp_path / "release_policy.json"
    matrix = tmp_path / "release_compat_matrix.json"
    out_path = tmp_path / "release_compat_matrix_report.json"

    _write_json(
        fixture,
        {
            "schema_version": "2.1",
            "trace_id": "x",
            "session_id": "s",
            "doc_id": "d",
            "request_id": "r",
            "state": "S02_DOC_READY",
            "state_rev": 1,
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:01+00:00",
        },
    )
    _write_json(
        policy,
        {
            "version": 1,
            "app_version": "0.1.0",
            "state_schema": {"current": "2.1", "backward_read_compatible": ["2.1"]},
            "runtime_data": {"files": []},
        },
    )
    _write_json(
        matrix,
        {
            "version": 1,
            "cases": [
                {
                    "id": "upgrade_current_to_current",
                    "direction": "upgrade",
                    "from_version": "0.1.0",
                    "to_version": "0.1.0",
                    "from_schema": "2.1",
                    "to_schema": "2.1",
                    "state_fixture": fixture.as_posix(),
                    "expect_readable": True,
                },
                {
                    "id": "rollback_current_to_current",
                    "direction": "rollback",
                    "from_version": "0.1.0",
                    "to_version": "0.1.0",
                    "from_schema": "2.1",
                    "to_schema": "2.1",
                    "state_fixture": fixture.as_posix(),
                    "expect_readable": True,
                },
            ],
            "rules": {
                "require_upgrade_case_for_current_schema": True,
                "require_rollback_case_for_current_schema": True,
                "require_n_plus_one_upgrade_case": True,
                "require_n_plus_one_rollback_case": True,
                "enforce_runtime_contract": False,
            },
        },
    )

    code, body = _run_matrix(monkeypatch, policy=policy, matrix=matrix, out_path=out_path, strict=True)
    assert code == 2
    checks = {str(row.get("id")): bool(row.get("ok")) for row in body["checks"]}
    assert checks["matrix_covers_n_plus_one_upgrade_case"] is False
    assert checks["matrix_covers_n_plus_one_rollback_case"] is False


def test_release_compat_matrix_strict_fails_when_negative_case_expected_failures_do_not_match(
    monkeypatch, tmp_path: Path
) -> None:
    fixture = tmp_path / "state_context.json"
    bad = tmp_path / "state_context_bad.json"
    policy = tmp_path / "release_policy.json"
    matrix = tmp_path / "release_compat_matrix.json"
    out_path = tmp_path / "release_compat_matrix_report.json"

    _write_json(
        fixture,
        {
            "schema_version": "2.1",
            "trace_id": "x",
            "session_id": "s",
            "doc_id": "d",
            "request_id": "r",
            "state": "S02_DOC_READY",
            "state_rev": 1,
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:00:01+00:00",
        },
    )
    _write_json(bad, [{"invalid": True}])
    _write_json(
        policy,
        {
            "version": 1,
            "app_version": "0.1.0",
            "state_schema": {"current": "2.1", "backward_read_compatible": ["2.1"]},
            "runtime_data": {"files": []},
        },
    )
    _write_json(
        matrix,
        {
            "version": 1,
            "cases": [
                {
                    "id": "upgrade_current_to_current",
                    "direction": "upgrade",
                    "from_version": "0.1.0",
                    "to_version": "0.1.0",
                    "from_schema": "2.1",
                    "to_schema": "2.1",
                    "state_fixture": fixture.as_posix(),
                    "expect_readable": True,
                },
                {
                    "id": "negative_case_bad_fixture",
                    "direction": "rollback",
                    "from_version": "0.2.0",
                    "to_version": "0.1.0",
                    "from_schema": "2.2",
                    "to_schema": "2.1",
                    "state_fixture": bad.as_posix(),
                    "expect_readable": False,
                    "expected_failed_checks": ["non_existent_failure_id"],
                },
            ],
            "rules": {
                "require_upgrade_case_for_current_schema": True,
                "require_rollback_case_for_current_schema": False,
                "require_failure_mode_case": True,
                "enforce_runtime_contract": False,
            },
        },
    )

    code, body = _run_matrix(monkeypatch, policy=policy, matrix=matrix, out_path=out_path, strict=True)
    assert code == 2
    bad_case = next(item for item in body["cases"] if str(item.get("id")) == "negative_case_bad_fixture")
    assert bad_case["ok"] is False
    bad_check = next(
        row for row in bad_case["checks"] if str(row.get("id")) == "negative_case_failure_expectation"
    )
    assert bad_check["ok"] is False
