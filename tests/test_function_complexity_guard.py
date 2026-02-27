from __future__ import annotations

from pathlib import Path

from scripts.guard_function_complexity import evaluate, load_policy


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body.strip() + "\n", encoding="utf-8")


def _base_policy() -> dict:
    return {
        "include": ["*.py", "**/*.py"],
        "exclude": [],
        "default_limits": {
            "max_function_lines": 30,
            "max_parameters": 4,
            "max_cyclomatic": 8,
        },
        "file_overrides": {},
        "overrides": {},
    }


def test_function_complexity_guard_passes_within_limits(tmp_path: Path) -> None:
    _write(
        tmp_path / "sample.py",
        """
def ok(a, b):
    if a:
        return b
    return a
""",
    )
    result = evaluate(tmp_path, _base_policy())
    assert result["ok"] is True
    assert result["violations"] == []


def test_function_complexity_guard_detects_function_line_violation(tmp_path: Path) -> None:
    _write(
        tmp_path / "sample.py",
        """
def too_long():
    x = 0
    x = 1
    x = 2
    x = 3
    x = 4
    x = 5
    x = 6
    x = 7
    x = 8
    x = 9
    x = 10
    x = 11
    x = 12
    x = 13
    x = 14
    x = 15
    x = 16
    x = 17
    x = 18
    x = 19
    x = 20
    return x
""",
    )
    policy = _base_policy()
    policy["default_limits"]["max_function_lines"] = 10
    result = evaluate(tmp_path, policy)
    assert result["ok"] is False
    assert any(v["metric"] == "function_lines" for v in result["violations"])


def test_function_complexity_guard_detects_parameter_violation(tmp_path: Path) -> None:
    _write(
        tmp_path / "sample.py",
        """
def too_many(a, b, c, d, e, f):
    return a + b + c + d + e + f
""",
    )
    policy = _base_policy()
    policy["default_limits"]["max_parameters"] = 4
    result = evaluate(tmp_path, policy)
    assert result["ok"] is False
    assert any(v["metric"] == "parameter_count" for v in result["violations"])


def test_function_complexity_guard_detects_cyclomatic_violation_and_honors_override(tmp_path: Path) -> None:
    _write(
        tmp_path / "sample.py",
        """
def branchy(x):
    if x > 0:
        x -= 1
    if x > 1:
        x -= 1
    if x > 2:
        x -= 1
    if x > 3:
        x -= 1
    if x > 4:
        x -= 1
    return x
""",
    )
    policy = _base_policy()
    policy["default_limits"]["max_cyclomatic"] = 3
    result = evaluate(tmp_path, policy)
    assert result["ok"] is False
    assert any(v["metric"] == "cyclomatic_complexity" for v in result["violations"])

    override_policy = _base_policy()
    override_policy["default_limits"]["max_cyclomatic"] = 3
    override_policy["overrides"] = {
        "sample.py::branchy": {
            "max_cyclomatic": 10,
        }
    }
    result2 = evaluate(tmp_path, override_policy)
    assert result2["ok"] is True


def test_repo_function_complexity_policy_is_valid_and_green() -> None:
    root = Path(__file__).resolve().parents[1]
    policy = load_policy(root / "security" / "function_complexity_limits.json")
    result = evaluate(root, policy)
    assert result["ok"] is True
