"""Guard Function Complexity command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import argparse
import ast
import json
import time
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path
from typing import Any


@dataclass
class FunctionMetric:
    path: str
    qualname: str
    lineno: int
    end_lineno: int
    function_lines: int
    parameter_count: int
    cyclomatic_complexity: int

    @property
    def function_id(self) -> str:
        return f"{self.path}::{self.qualname}"


class _FunctionCollector(ast.NodeVisitor):
    def __init__(self, path: str) -> None:
        self.path = path
        self._stack: list[str] = []
        self.metrics: list[FunctionMetric] = []

    def _push(self, name: str) -> None:
        self._stack.append(str(name))

    def _pop(self) -> None:
        if self._stack:
            self._stack.pop()

    def _qualname(self, name: str) -> str:
        if not self._stack:
            return str(name)
        return ".".join([*self._stack, str(name)])

    def _parameter_count(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
        args = node.args
        positional = [*list(args.posonlyargs), *list(args.args)]
        count = len(positional) + len(args.kwonlyargs)
        if args.vararg is not None:
            count += 1
        if args.kwarg is not None:
            count += 1
        if positional and positional[0].arg in {"self", "cls"}:
            count -= 1
        return max(0, count)

    def _cyclomatic_complexity(self, node: ast.AST) -> int:
        complexity = 1
        for item in ast.walk(node):
            if isinstance(item, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.IfExp, ast.ExceptHandler, ast.Assert)):
                complexity += 1
            elif isinstance(item, ast.BoolOp):
                complexity += max(1, len(item.values) - 1)
            elif isinstance(item, ast.Try):
                complexity += len(item.handlers)
                if item.orelse:
                    complexity += 1
            elif isinstance(item, ast.comprehension):
                complexity += 1 + len(item.ifs)
            elif isinstance(item, ast.Match):
                for case in item.cases:
                    is_wildcard = isinstance(case.pattern, ast.MatchAs) and case.pattern.name is None
                    if not is_wildcard:
                        complexity += 1
                    if case.guard is not None:
                        complexity += 1
        return complexity

    def _record(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        end_lineno = int(getattr(node, "end_lineno", node.lineno) or node.lineno)
        lineno = int(node.lineno or 0)
        self.metrics.append(
            FunctionMetric(
                path=self.path,
                qualname=self._qualname(node.name),
                lineno=lineno,
                end_lineno=end_lineno,
                function_lines=max(1, end_lineno - lineno + 1),
                parameter_count=self._parameter_count(node),
                cyclomatic_complexity=self._cyclomatic_complexity(node),
            )
        )

    def visit_ClassDef(self, node: ast.ClassDef) -> Any:  # noqa: ANN401
        self._push(node.name)
        self.generic_visit(node)
        self._pop()
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:  # noqa: ANN401
        self._record(node)
        self._push(node.name)
        self.generic_visit(node)
        self._pop()
        return node

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> Any:  # noqa: ANN401
        self._record(node)
        self._push(node.name)
        self.generic_visit(node)
        self._pop()
        return node


def _as_posix(path: Path) -> str:
    return path.as_posix()


def load_policy(path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    include = list(raw.get("include") or [])
    exclude = list(raw.get("exclude") or [])
    default_limits = dict(raw.get("default_limits") or {})
    file_overrides = dict(raw.get("file_overrides") or {})
    overrides = dict(raw.get("overrides") or {})
    return {
        "include": include,
        "exclude": exclude,
        "default_limits": default_limits,
        "file_overrides": file_overrides,
        "overrides": overrides,
    }


def _matches_any(rel_path: str, patterns: list[str]) -> bool:
    for pat in patterns:
        if fnmatch(rel_path, pat):
            return True
    return False


def collect_target_files(root: Path, include: list[str], exclude: list[str]) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*.py"):
        if not path.is_file():
            continue
        rel = _as_posix(path.relative_to(root))
        if include and not _matches_any(rel, include):
            continue
        if exclude and _matches_any(rel, exclude):
            continue
        files.append(path)
    files.sort(key=lambda p: _as_posix(p.relative_to(root)))
    return files


def _limits_for(function_id: str, rel_path: str, policy: dict) -> dict:
    defaults = policy.get("default_limits") or {}
    row = {
        "max_function_lines": int(defaults.get("max_function_lines", 0) or 0),
        "max_parameters": int(defaults.get("max_parameters", 0) or 0),
        "max_cyclomatic": int(defaults.get("max_cyclomatic", 0) or 0),
    }
    file_overrides = policy.get("file_overrides") or {}
    file_row = file_overrides.get(rel_path) if isinstance(file_overrides, dict) else None
    if isinstance(file_row, dict):
        for key in ("max_function_lines", "max_parameters", "max_cyclomatic"):
            if key in file_row and file_row.get(key) is not None:
                row[key] = int(file_row.get(key))
    overrides = policy.get("overrides") or {}
    fn_row = overrides.get(function_id) if isinstance(overrides, dict) else None
    if isinstance(fn_row, dict):
        for key in ("max_function_lines", "max_parameters", "max_cyclomatic"):
            if key in fn_row and fn_row.get(key) is not None:
                row[key] = int(fn_row.get(key))
    return row


def _collect_functions(root: Path, targets: list[Path]) -> list[FunctionMetric]:
    out: list[FunctionMetric] = []
    for path in targets:
        rel = _as_posix(path.relative_to(root))
        source = path.read_text(encoding="utf-8-sig", errors="ignore")
        try:
            tree = ast.parse(source)
        except Exception:
            continue
        collector = _FunctionCollector(rel)
        collector.visit(tree)
        out.extend(collector.metrics)
    out.sort(key=lambda row: (row.path, row.lineno, row.qualname))
    return out


def evaluate(root: Path, policy: dict) -> dict:
    include = list(policy.get("include") or [])
    exclude = list(policy.get("exclude") or [])
    targets = collect_target_files(root, include, exclude)
    functions = _collect_functions(root, targets)

    checked: list[dict] = []
    violations: list[dict] = []
    for row in functions:
        limits = _limits_for(row.function_id, row.path, policy)
        entry = {
            "id": row.function_id,
            "path": row.path,
            "qualname": row.qualname,
            "lineno": row.lineno,
            "end_lineno": row.end_lineno,
            "function_lines": row.function_lines,
            "parameter_count": row.parameter_count,
            "cyclomatic_complexity": row.cyclomatic_complexity,
            "limits": limits,
        }
        checked.append(entry)

        max_lines = int(limits.get("max_function_lines", 0) or 0)
        max_params = int(limits.get("max_parameters", 0) or 0)
        max_cyclomatic = int(limits.get("max_cyclomatic", 0) or 0)
        if max_lines > 0 and row.function_lines > max_lines:
            violations.append({**entry, "metric": "function_lines", "value": row.function_lines, "limit": max_lines})
        if max_params > 0 and row.parameter_count > max_params:
            violations.append({**entry, "metric": "parameter_count", "value": row.parameter_count, "limit": max_params})
        if max_cyclomatic > 0 and row.cyclomatic_complexity > max_cyclomatic:
            violations.append(
                {**entry, "metric": "cyclomatic_complexity", "value": row.cyclomatic_complexity, "limit": max_cyclomatic}
            )

    return {
        "ok": len(violations) == 0,
        "checked_count": len(checked),
        "violations": violations,
        "checked": checked,
    }


def _default_out_path() -> Path:
    return Path(".data/out") / f"function_complexity_guard_{int(time.time())}.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Guard Python function complexity limits.")
    parser.add_argument("--config", default="security/function_complexity_limits.json", help="Policy json path.")
    parser.add_argument("--root", default=".", help="Repository root.")
    parser.add_argument("--out", default="", help="Report output path.")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = (root / config_path).resolve()
    if not config_path.exists():
        report = {"ok": False, "error": f"config not found: {config_path.as_posix()}"}
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2

    policy = load_policy(config_path)
    result = evaluate(root, policy)
    report = {
        "ok": bool(result.get("ok")),
        "config": _as_posix(config_path),
        "root": _as_posix(root),
        "checked_count": int(result.get("checked_count", 0)),
        "violation_count": len(result.get("violations") or []),
        "violations": result.get("violations") or [],
    }
    out_path = Path(str(args.out or "")).resolve() if str(args.out or "").strip() else _default_out_path()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
