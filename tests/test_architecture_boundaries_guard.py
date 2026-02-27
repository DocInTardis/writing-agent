from __future__ import annotations

from pathlib import Path

from scripts.guard_architecture_boundaries import evaluate, load_policy


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body.strip() + "\n", encoding="utf-8")


def _policy() -> dict:
    return {
        "include": ["pkg/**/*.py", "pkg/*.py"],
        "exclude": [],
        "layers": {
            "api": {
                "path_patterns": ["pkg/api/**/*.py", "pkg/api/*.py"],
                "module_prefixes": ["pkg.api"],
            },
            "services": {
                "path_patterns": ["pkg/services/**/*.py", "pkg/services/*.py"],
                "module_prefixes": ["pkg.services"],
            },
            "domains": {
                "path_patterns": ["pkg/domains/**/*.py", "pkg/domains/*.py"],
                "module_prefixes": ["pkg.domains"],
            },
            "app": {
                "path_patterns": ["pkg/app.py"],
                "module_prefixes": ["pkg.app"],
            },
        },
        "forbidden_dependencies": {
            "api": ["app"],
            "services": ["api", "app"],
            "domains": ["services", "api", "app"],
        },
        "allow": [],
    }


def test_architecture_guard_passes_on_allowed_edges(tmp_path: Path) -> None:
    _write(tmp_path / "pkg" / "api" / "routes.py", "from pkg.services.work import run\n")
    _write(tmp_path / "pkg" / "services" / "work.py", "from pkg.domains.types import X\n")
    _write(tmp_path / "pkg" / "domains" / "types.py", "class X:\n    pass\n")
    result = evaluate(tmp_path, _policy())
    assert result["ok"] is True
    assert result["violation_count"] == 0


def test_architecture_guard_blocks_forbidden_dependency(tmp_path: Path) -> None:
    _write(tmp_path / "pkg" / "api" / "routes.py", "from pkg.app import app\n")
    _write(tmp_path / "pkg" / "app.py", "app = object()\n")
    result = evaluate(tmp_path, _policy())
    assert result["ok"] is False
    assert result["violation_count"] == 1
    row = result["violations"][0]
    assert row["source_layer"] == "api"
    assert row["target_layer"] == "app"


def test_architecture_guard_allows_allowlisted_edge(tmp_path: Path) -> None:
    _write(tmp_path / "pkg" / "api" / "legacy.py", "from pkg.app import app\n")
    _write(tmp_path / "pkg" / "app.py", "app = object()\n")
    policy = _policy()
    policy["allow"] = [{"source_path": "pkg/api/legacy.py", "target_module": "pkg.app"}]
    result = evaluate(tmp_path, policy)
    assert result["ok"] is True
    assert result["violation_count"] == 0


def test_repo_architecture_policy_is_valid_and_green() -> None:
    root = Path(__file__).resolve().parents[1]
    policy = load_policy(root / "security" / "architecture_boundaries.json")
    result = evaluate(root, policy)
    assert result["ok"] is True
