from __future__ import annotations

from scripts import release_governance_check


def test_release_governance_semver_parser() -> None:
    assert release_governance_check._is_semver("1.2.3")
    assert release_governance_check._is_semver("1.2.3-rc1")
    assert not release_governance_check._is_semver("1.2")
    assert not release_governance_check._is_semver("v1.2.3")


def test_release_governance_schema_parser() -> None:
    assert release_governance_check._is_schema_version("2.1")
    assert not release_governance_check._is_schema_version("2")
    assert not release_governance_check._is_schema_version("2.1.0")


def test_dependency_baseline_validator_accepts_expected_shape() -> None:
    data = {
        "version": 1,
        "levels": {
            "npm_prod": {"info": 0, "low": 0, "moderate": 0, "high": 0, "critical": 0, "unknown": 0, "total": 0},
            "npm_dev": {"info": 0, "low": 0, "moderate": 0, "high": 0, "critical": 0, "unknown": 0, "total": 0},
            "pip": {"info": 0, "low": 0, "moderate": 0, "high": 0, "critical": 0, "unknown": 0, "total": 0},
        },
    }
    assert release_governance_check._validate_dependency_baseline(data)


def test_extract_version_and_schema_from_source() -> None:
    init_text = '__version__ = "0.9.1"'
    ctx_text = 'schema_version="3.2"'
    assert release_governance_check._extract_app_version(init_text) == "0.9.1"
    assert release_governance_check._extract_schema_version(ctx_text) == "3.2"
