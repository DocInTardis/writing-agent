"""Rust Bridge module.

This module belongs to `writing_agent.v2` in the writing-agent codebase.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def try_rust_docx_export(text: str) -> bytes | None:
    if os.environ.get("WA_USE_RUST_ENGINE") != "1":
        return None
    exe = REPO_ROOT / "engine" / "target" / "release" / "wa_export.exe"
    if not exe.exists():
        exe = REPO_ROOT / "engine" / "target" / "debug" / "wa_export.exe"
        if not exe.exists():
            return None
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            in_path = Path(tmpdir) / "input.md"
            out_path = Path(tmpdir) / "output.docx"
            in_path.write_text(text, encoding="utf-8")
            result = subprocess.run(
                [str(exe), str(in_path), str(out_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0 or not out_path.exists():
                return None
            return out_path.read_bytes()
    except Exception:
        return None


def try_rust_import(path: Path) -> str | None:
    if os.environ.get("WA_USE_RUST_ENGINE") != "1":
        return None
    exe = REPO_ROOT / "engine" / "target" / "release" / "wa_import.exe"
    if not exe.exists():
        exe = REPO_ROOT / "engine" / "target" / "debug" / "wa_import.exe"
        if not exe.exists():
            return None
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "output.md"
            result = subprocess.run(
                [str(exe), str(path), str(out_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode != 0 or not out_path.exists():
                return None
            return out_path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return None
