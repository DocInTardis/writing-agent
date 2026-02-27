from __future__ import annotations

from pathlib import Path

from scripts.guard_file_line_limits import evaluate, load_policy


def _write_lines(path: Path, count: int) -> None:
    body = "\n".join([f"line_{i}" for i in range(count)])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_line_guard_passes_within_default_limit(tmp_path: Path) -> None:
    _write_lines(tmp_path / "writing_agent" / "demo.py", 20)
    policy = {
        "include": ["writing_agent/**/*.py"],
        "exclude": [],
        "default_limits": {".py": 30},
        "overrides": {},
    }
    result = evaluate(tmp_path, policy)
    assert result["ok"] is True
    assert result["violations"] == []


def test_line_guard_detects_override_violation(tmp_path: Path) -> None:
    rel = "writing_agent/web/huge.py"
    _write_lines(tmp_path / rel, 25)
    policy = {
        "include": ["writing_agent/**/*.py"],
        "exclude": [],
        "default_limits": {".py": 200},
        "overrides": {rel: 10},
    }
    result = evaluate(tmp_path, policy)
    assert result["ok"] is False
    assert len(result["violations"]) == 1
    row = result["violations"][0]
    assert row["path"] == rel
    assert row["lines"] == 25
    assert row["limit"] == 10


def test_repo_policy_covers_current_app_v2_size() -> None:
    root = Path(__file__).resolve().parents[1]
    policy_path = root / "security" / "file_line_limits.json"
    policy = load_policy(policy_path)
    assert int((policy.get("default_limits") or {}).get(".py") or 0) <= 1000
    assert "writing_agent/web/app_v2.py" in policy["overrides"]
    limit = int(policy["overrides"]["writing_agent/web/app_v2.py"])
    app_lines = len((root / "writing_agent" / "web" / "app_v2.py").read_text(encoding="utf-8-sig").splitlines())
    assert app_lines <= limit


def test_repo_policy_covers_current_large_script_sizes() -> None:
    root = Path(__file__).resolve().parents[1]
    policy = load_policy(root / "security" / "file_line_limits.json")
    for rel in ("scripts/release_preflight.py", "scripts/release_rollout_executor.py"):
        assert rel in policy["overrides"]
        limit = int(policy["overrides"][rel])
        lines = len((root / rel).read_text(encoding="utf-8-sig").splitlines())
        assert lines <= limit
