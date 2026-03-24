from __future__ import annotations

from pathlib import Path

from scripts.guard_repo_hygiene import evaluate, evaluate_paths, load_policy


def _policy() -> dict:
    return {
        "forbidden_roots": ["deliverables", "tmp"],
        "forbidden_globs": [".tmp_*", "**/__pycache__/**"],
        "allow": [],
    }


def test_repo_hygiene_blocks_generated_root() -> None:
    result = evaluate_paths(["deliverables/run_1/output.json", "writing_agent/app.py"], _policy())
    assert result["ok"] is False
    assert result["violation_count"] == 1
    row = result["violations"][0]
    assert row["path"] == "deliverables/run_1/output.json"
    assert row["kind"] == "forbidden_root"
    assert row["rule"] == "deliverables"


def test_repo_hygiene_blocks_temp_file_glob() -> None:
    result = evaluate_paths([".tmp_probe.txt", "scripts/tool.py"], _policy())
    assert result["ok"] is False
    assert result["violation_count"] == 1
    row = result["violations"][0]
    assert row["path"] == ".tmp_probe.txt"
    assert row["kind"] == "forbidden_glob"
    assert row["rule"] == ".tmp_*"


def test_repo_hygiene_respects_allowlist() -> None:
    policy = _policy()
    policy["allow"] = ["tests/fixtures/**"]
    result = evaluate_paths(["tests/fixtures/generated.json", "writing_agent/app.py"], policy)
    assert result["ok"] is True
    assert result["violation_count"] == 0


def test_repo_hygiene_blocks_nested_forbidden_glob() -> None:
    policy = _policy()
    policy["forbidden_globs"] = ["scripts/dev/**"]
    result = evaluate_paths(["scripts/dev/debug_generation.py", "scripts/run_quality_suite.py"], policy)
    assert result["ok"] is False
    assert result["violation_count"] == 1
    row = result["violations"][0]
    assert row["path"] == "scripts/dev/debug_generation.py"
    assert row["rule"] == "scripts/dev/**"


def test_repo_hygiene_repo_policy_is_valid_and_green() -> None:
    root = Path(__file__).resolve().parents[1]
    policy = load_policy(root / "security" / "repo_hygiene_policy.json")
    result = evaluate(root, policy)
    assert result["ok"] is True, result["violations"]
