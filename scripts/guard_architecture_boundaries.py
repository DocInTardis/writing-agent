"""Guard Architecture Boundaries command utility.

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


def _as_posix(path: Path) -> str:
    return path.as_posix()


def _matches_any(text: str, patterns: list[str]) -> bool:
    for pat in patterns:
        if fnmatch(text, pat):
            return True
    return False


@dataclass
class ImportEdge:
    source_path: str
    source_module: str
    source_layer: str
    target_module: str
    target_layer: str
    lineno: int
    kind: str


def load_policy(path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    include = list(raw.get("include") or [])
    exclude = list(raw.get("exclude") or [])
    layers = dict(raw.get("layers") or {})
    forbidden = dict(raw.get("forbidden_dependencies") or {})
    allow = list(raw.get("allow") or [])
    return {
        "include": include,
        "exclude": exclude,
        "layers": layers,
        "forbidden_dependencies": forbidden,
        "allow": allow,
    }


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


def _module_from_rel_path(rel_path: str) -> str:
    path = Path(rel_path)
    if path.name == "__init__.py":
        return ".".join(path.with_suffix("").parts[:-1])
    return ".".join(path.with_suffix("").parts)


def _layer_by_path(rel_path: str, policy: dict) -> str:
    layers = policy.get("layers") if isinstance(policy.get("layers"), dict) else {}
    for layer_name, cfg in layers.items():
        row = cfg if isinstance(cfg, dict) else {}
        patterns = [str(x) for x in (row.get("path_patterns") or []) if str(x)]
        if patterns and _matches_any(rel_path, patterns):
            return str(layer_name)
    return ""


def _layer_by_module(module_name: str, policy: dict) -> str:
    layers = policy.get("layers") if isinstance(policy.get("layers"), dict) else {}
    for layer_name, cfg in layers.items():
        row = cfg if isinstance(cfg, dict) else {}
        prefixes = [str(x) for x in (row.get("module_prefixes") or []) if str(x)]
        for prefix in prefixes:
            if module_name == prefix or module_name.startswith(prefix + "."):
                return str(layer_name)
    return ""


def _resolve_from_module(source_module: str, module: str | None, level: int) -> str:
    source_parts = source_module.split(".")
    pkg_parts = source_parts[:-1]
    mod = str(module or "").strip()
    if level <= 0:
        return mod
    up = max(0, level - 1)
    if up > len(pkg_parts):
        pkg_parts = []
    else:
        pkg_parts = pkg_parts[: len(pkg_parts) - up]
    if mod:
        if pkg_parts:
            return ".".join([*pkg_parts, *mod.split(".")])
        return mod
    return ".".join(pkg_parts)


def _collect_import_modules(source_module: str, node: ast.AST) -> list[tuple[str, int, str]]:
    rows: list[tuple[str, int, str]] = []
    if isinstance(node, ast.Import):
        for alias in node.names:
            mod = str(alias.name or "").strip()
            if mod:
                rows.append((mod, int(getattr(node, "lineno", 0) or 0), "import"))
    elif isinstance(node, ast.ImportFrom):
        base = _resolve_from_module(source_module, node.module, int(node.level or 0))
        lineno = int(getattr(node, "lineno", 0) or 0)
        if node.module is None and base:
            for alias in node.names:
                name = str(alias.name or "").strip()
                if not name or name == "*":
                    continue
                rows.append((f"{base}.{name}", lineno, "from"))
        elif base:
            rows.append((base, lineno, "from"))
    return rows


def _is_allowed(edge: ImportEdge, allow_rules: list[dict]) -> bool:
    for raw in allow_rules:
        row = raw if isinstance(raw, dict) else {}
        source_path_pat = str(row.get("source_path") or "").strip()
        source_mod_pat = str(row.get("source_module") or "").strip()
        target_mod_pat = str(row.get("target_module") or "").strip()
        target_layer = str(row.get("target_layer") or "").strip()
        source_layer = str(row.get("source_layer") or "").strip()

        if source_path_pat and (not fnmatch(edge.source_path, source_path_pat)):
            continue
        if source_mod_pat and (not fnmatch(edge.source_module, source_mod_pat)):
            continue
        if target_mod_pat and (not fnmatch(edge.target_module, target_mod_pat)):
            continue
        if target_layer and edge.target_layer != target_layer:
            continue
        if source_layer and edge.source_layer != source_layer:
            continue
        return True
    return False


def evaluate(root: Path, policy: dict) -> dict:
    include = list(policy.get("include") or [])
    exclude = list(policy.get("exclude") or [])
    allow_rules = [x for x in list(policy.get("allow") or []) if isinstance(x, dict)]
    forbidden = policy.get("forbidden_dependencies") if isinstance(policy.get("forbidden_dependencies"), dict) else {}

    targets = collect_target_files(root, include, exclude)
    checked_edges: list[dict] = []
    violations: list[dict] = []

    for path in targets:
        rel = _as_posix(path.relative_to(root))
        source_layer = _layer_by_path(rel, policy)
        if not source_layer:
            continue
        source_module = _module_from_rel_path(rel)
        try:
            source = path.read_text(encoding="utf-8-sig", errors="ignore")
            tree = ast.parse(source)
        except Exception:
            continue

        forbidden_targets = {str(x) for x in list(forbidden.get(source_layer) or []) if str(x)}
        if not forbidden_targets:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.Import, ast.ImportFrom)):
                continue
            imports = _collect_import_modules(source_module, node)
            for target_module, lineno, kind in imports:
                target_layer = _layer_by_module(target_module, policy)
                if not target_layer:
                    continue
                row = ImportEdge(
                    source_path=rel,
                    source_module=source_module,
                    source_layer=source_layer,
                    target_module=target_module,
                    target_layer=target_layer,
                    lineno=lineno,
                    kind=kind,
                )
                checked_edges.append(
                    {
                        "source_path": row.source_path,
                        "source_module": row.source_module,
                        "source_layer": row.source_layer,
                        "target_module": row.target_module,
                        "target_layer": row.target_layer,
                        "lineno": row.lineno,
                        "kind": row.kind,
                    }
                )
                if row.target_layer not in forbidden_targets:
                    continue
                if _is_allowed(row, allow_rules):
                    continue
                violations.append(
                    {
                        "source_path": row.source_path,
                        "source_module": row.source_module,
                        "source_layer": row.source_layer,
                        "target_module": row.target_module,
                        "target_layer": row.target_layer,
                        "lineno": row.lineno,
                        "kind": row.kind,
                        "rule": f"{row.source_layer} -> {row.target_layer}",
                    }
                )

    return {
        "ok": len(violations) == 0,
        "checked_count": len(checked_edges),
        "violation_count": len(violations),
        "violations": violations,
        "checked": checked_edges,
    }


def _default_out_path() -> Path:
    return Path(".data/out") / f"architecture_boundaries_guard_{int(time.time())}.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Guard architecture boundary dependencies.")
    parser.add_argument("--config", default="security/architecture_boundaries.json", help="Policy json path.")
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
        "violation_count": int(result.get("violation_count", 0)),
        "violations": result.get("violations") or [],
    }
    out_path = Path(str(args.out or "")).resolve() if str(args.out or "").strip() else _default_out_path()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
