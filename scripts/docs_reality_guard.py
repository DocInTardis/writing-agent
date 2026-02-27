#!/usr/bin/env python3
"""Docs Reality Guard command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


_FENCE_RE = re.compile(r"```[^\n]*\n(.*?)```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_PATH_HINT_RE = re.compile(r"[A-Za-z0-9_.-]+[/\\][A-Za-z0-9_.\-/*\\]+")


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _load_json_dict(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def _check_row(*, check_id: str, ok: bool, value: Any, expect: str, mode: str = "enforce") -> dict[str, Any]:
    return {
        "id": str(check_id),
        "ok": bool(ok),
        "value": value,
        "expect": str(expect),
        "mode": str(mode or "enforce"),
    }


def _collect_docs(globs_in: list[str]) -> list[Path]:
    out: list[Path] = []
    seen: set[str] = set()
    for pattern in globs_in:
        for raw in sorted(glob.glob(str(pattern), recursive=True)):
            path = Path(raw)
            if not path.exists() or (not path.is_file()):
                continue
            key = path.resolve().as_posix().lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(path)
    return out


def _normalize_path_like(token: str) -> str:
    text = str(token or "").strip().strip("`").strip("\"").strip("'")
    text = text.replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text


def _should_check_path(path_like: str, prefixes: list[str]) -> bool:
    text = str(path_like or "").strip()
    if not text:
        return False
    if text.startswith(("http://", "https://", "vscode://", "file://")):
        return False
    return any(text.startswith(prefix) for prefix in prefixes)


def _path_exists(path_like: str) -> bool:
    text = str(path_like or "").strip()
    if not text:
        return False
    if "*" in text or "?" in text:
        return len(glob.glob(text, recursive=True)) > 0
    return Path(text).exists()


def _extract_path_refs(text: str) -> list[str]:
    refs: set[str] = set()

    def _add_candidate(raw_token: str) -> None:
        token = _normalize_path_like(raw_token)
        if not token:
            return
        token = token.strip("()[]{}<>.,;")
        if _PATH_HINT_RE.search(token):
            refs.add(token)

    for m in _INLINE_CODE_RE.finditer(str(text or "")):
        token = _normalize_path_like(m.group(1))
        first = token.split()[0] if " " in token else token
        lowered = token.lower()
        command_like = (
            (" " in token)
            and (
                lowered.startswith("scripts/")
                or lowered.startswith("python ")
                or lowered.startswith(".\\.venv\\scripts\\python ")
                or lowered.startswith(".venv\\scripts\\python ")
                or (" --" in token)
            )
            and _PATH_HINT_RE.search(first)
        )
        if command_like:
            _add_candidate(first)
        else:
            _add_candidate(token)
    return sorted(refs)


def _extract_command_lines(text: str) -> list[str]:
    lines: list[str] = []
    for m in _FENCE_RE.finditer(str(text or "")):
        block = str(m.group(1) or "")
        for raw_line in block.splitlines():
            line = str(raw_line or "").strip()
            if not line:
                continue
            lowered = line.lower()
            if lowered.startswith("python ") or lowered.startswith(".\\.venv\\scripts\\python ") or lowered.startswith(".venv\\scripts\\python "):
                lines.append(line)
    return lines


def _normalize_python_command(line: str) -> list[str]:
    text = str(line or "").strip()
    lowered = text.lower()
    if lowered.startswith(".\\.venv\\scripts\\python "):
        text = "python " + text[len(".\\.venv\\Scripts\\python ") :]
    elif lowered.startswith(".venv\\scripts\\python "):
        text = "python " + text[len(".venv\\Scripts\\python ") :]
    try:
        argv = shlex.split(text, posix=False)
    except Exception:
        argv = text.split()
    return [arg for arg in argv if str(arg) != "`"]


def _build_help_check(argv: list[str]) -> tuple[list[str], str]:
    if len(argv) < 2:
        return ([], "too_short")
    if str(argv[0]).lower() != "python":
        return ([], "not_python_command")
    if argv[1] == "-m":
        # Module entrypoints may run long-lived processes; skip hard execution.
        return ([], "module_command_skipped")
    if argv[1].replace("\\", "/").startswith("scripts/") and argv[1].lower().endswith(".py"):
        script = argv[1].replace("\\", "/")
        if not Path(script).exists():
            return ([], "script_missing")
        return ([sys.executable, script, "--help"], "")
    return ([], "not_supported_pattern")


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify that documentation references and commands match real project assets.")
    parser.add_argument("--policy", default="security/docs_reality_policy.json")
    parser.add_argument("--doc-glob", action="append", default=[])
    parser.add_argument("--path-prefix", action="append", default=[])
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--require-python-command-check", action="store_true")
    parser.add_argument("--max-missing-paths", type=int, default=-1)
    parser.add_argument("--max-command-failures", type=int, default=-1)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    started = time.time()
    policy_path = Path(str(args.policy))
    policy = _load_json_dict(policy_path)

    configured_globs = [str(x) for x in (policy.get("doc_globs") if isinstance(policy.get("doc_globs"), list) else []) if str(x).strip()]
    configured_prefixes = [str(x) for x in (policy.get("path_prefixes") if isinstance(policy.get("path_prefixes"), list) else []) if str(x).strip()]
    doc_globs = [str(x) for x in args.doc_glob if str(x).strip()] or configured_globs or ["README.md", "docs/**/*.md"]
    path_prefixes = [str(x).replace("\\", "/") for x in args.path_prefix if str(x).strip()] or [str(x).replace("\\", "/") for x in configured_prefixes] or ["docs/", "scripts/", "security/", ".github/workflows/", "writing_agent/"]
    max_missing_paths = int(args.max_missing_paths) if int(args.max_missing_paths) >= 0 else max(0, _safe_int(policy.get("max_missing_paths"), 0))
    max_command_failures = int(args.max_command_failures) if int(args.max_command_failures) >= 0 else max(0, _safe_int(policy.get("max_command_failures"), 0))

    checks: list[dict[str, Any]] = []
    checks.append(
        _check_row(
            check_id="policy_loaded",
            ok=bool(policy),
            value=policy_path.as_posix(),
            expect="docs reality policy exists and is valid json",
            mode="warn",
        )
    )

    docs = _collect_docs(doc_globs)
    checks.append(
        _check_row(
            check_id="docs_scanned_non_empty",
            ok=len(docs) > 0,
            value={"count": len(docs), "doc_globs": doc_globs},
            expect="at least one markdown doc is scanned",
            mode="enforce",
        )
    )

    path_refs: set[str] = set()
    command_lines: list[dict[str, Any]] = []
    for path in docs:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            text = ""
        for ref in _extract_path_refs(text):
            path_refs.add(ref)
        for line in _extract_command_lines(text):
            command_lines.append({"doc": path.as_posix(), "line": line})

    checked_refs = sorted([ref for ref in path_refs if _should_check_path(ref, path_prefixes)])
    missing_paths = [ref for ref in checked_refs if not _path_exists(ref)]
    checks.append(
        _check_row(
            check_id="doc_referenced_paths_exist",
            ok=len(missing_paths) <= max_missing_paths,
            value={"missing_count": len(missing_paths), "allowed": max_missing_paths, "missing": missing_paths[:120]},
            expect="doc referenced source paths should exist",
            mode="enforce",
        )
    )

    command_checks: list[dict[str, Any]] = []
    command_failures: list[dict[str, Any]] = []
    if bool(args.require_python_command_check):
        for row in command_lines:
            line = str(row.get("line") or "")
            argv = _normalize_python_command(line)
            help_cmd, reason = _build_help_check(argv)
            status = {
                "doc": str(row.get("doc") or ""),
                "line": line,
                "argv": argv,
                "check_reason": reason,
                "checked": False,
                "ok": True,
                "return_code": 0,
                "stdout_tail": "",
                "stderr_tail": "",
            }
            if help_cmd:
                run = subprocess.run(help_cmd, text=True, capture_output=True)
                status["checked"] = True
                status["ok"] = int(run.returncode) == 0
                status["return_code"] = int(run.returncode)
                status["stdout_tail"] = str(run.stdout or "")[-400:]
                status["stderr_tail"] = str(run.stderr or "")[-400:]
            elif reason == "script_missing":
                status["checked"] = True
                status["ok"] = False
                status["return_code"] = 2
            command_checks.append(status)
            if not bool(status.get("ok")):
                command_failures.append(status)
    checks.append(
        _check_row(
            check_id="doc_python_commands_callable",
            ok=(not bool(args.require_python_command_check)) or (len(command_failures) <= max_command_failures),
            value={"failures": len(command_failures), "allowed": max_command_failures},
            expect="documented python script commands should be callable via --help",
            mode="enforce" if bool(args.require_python_command_check) else "warn",
        )
    )

    enforce_rows = [row for row in checks if str(row.get("mode") or "enforce") == "enforce"]
    ok = all(bool(row.get("ok")) for row in enforce_rows)
    ended = time.time()
    report = {
        "ok": bool(ok),
        "started_at": round(started, 3),
        "ended_at": round(ended, 3),
        "duration_s": round(ended - started, 3),
        "strict": bool(args.strict),
        "require_python_command_check": bool(args.require_python_command_check),
        "policy_file": policy_path.as_posix(),
        "docs_scanned": [path.as_posix() for path in docs],
        "path_prefixes": path_prefixes,
        "path_references_checked": checked_refs,
        "missing_paths": missing_paths,
        "command_checks": command_checks[:200],
        "command_failures": command_failures[:80],
        "checks": checks,
    }

    if bool(args.strict):
        # Strict mode enforces warn checks as well.
        report["ok"] = bool(report.get("ok")) and all(bool(row.get("ok")) for row in checks)

    out_default = Path(".data/out") / f"docs_reality_guard_{int(ended)}.json"
    out_path = Path(str(args.out or out_default))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if bool(report.get("ok")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
