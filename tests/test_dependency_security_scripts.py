from __future__ import annotations

from scripts import dependency_audit
from scripts import update_dependency_baseline


def test_dependency_audit_extract_json_recovers_from_prefixed_logs() -> None:
    raw = "npm notice some logs before json\n{\"metadata\":{\"vulnerabilities\":{\"high\":1}}}\ntrailer"
    data = dependency_audit._extract_json(raw)
    assert isinstance(data, dict)
    assert data["metadata"]["vulnerabilities"]["high"] == 1


def test_dependency_audit_npm_levels_from_metadata() -> None:
    payload = {
        "metadata": {
            "vulnerabilities": {
                "info": 2,
                "low": 3,
                "moderate": 4,
                "high": 5,
                "critical": 6,
            }
        }
    }
    levels = dependency_audit._npm_levels(payload)
    assert levels["critical"] == 6
    assert levels["high"] == 5
    assert levels["moderate"] == 4
    assert levels["total"] == 20


def test_dependency_audit_baseline_levels_defaults() -> None:
    baseline = {"levels": {"npm_prod": {"critical": 1}, "pip": {"total": 3}}}
    levels = dependency_audit._baseline_levels(baseline)
    assert levels["npm_prod"]["critical"] == 1
    assert levels["npm_prod"]["high"] == 0
    assert levels["npm_dev"]["total"] == 0
    assert levels["pip"]["total"] == 3


def test_update_dependency_baseline_find_regressions_only_increases() -> None:
    current = {
        "npm_prod": {"critical": 1, "high": 0, "moderate": 0, "total": 1},
        "npm_dev": {"critical": 0, "high": 2, "moderate": 2, "total": 4},
        "pip": {"critical": 0, "high": 0, "moderate": 0, "total": 0},
    }
    baseline = {
        "npm_prod": {"critical": 0, "high": 0, "moderate": 0, "total": 0},
        "npm_dev": {"critical": 0, "high": 3, "moderate": 2, "total": 5},
        "pip": {"critical": 0, "high": 0, "moderate": 0, "total": 0},
    }
    rows = update_dependency_baseline._find_regressions(current=current, baseline=baseline)
    assert any(row["group"] == "npm_prod" and row["severity"] == "critical" for row in rows)
    assert any(row["group"] == "npm_prod" and row["severity"] == "total" for row in rows)
    assert not any(row["group"] == "npm_dev" and row["severity"] == "high" for row in rows)
    assert not any(row["group"] == "npm_dev" and row["severity"] == "moderate" for row in rows)
