"""Rust Bridge module.

This module belongs to `writing_agent.v2` in the writing-agent codebase.
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _find_exe(name: str) -> Path | None:
    for profile in ("release", "debug"):
        candidate = REPO_ROOT / "engine" / "target" / profile / name
        if candidate.exists():
            return candidate
    return None


def try_rust_docx_export(text: str) -> bytes | None:
    if os.environ.get("WA_USE_RUST_ENGINE") != "1":
        return None
    exe = _find_exe("wa_export.exe")
    if exe is None:
        logger.debug("Rust wa_export binary not found")
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
            if result.returncode != 0:
                logger.warning("wa_export exited with %d: %s", result.returncode, result.stderr.strip())
                return None
            if not out_path.exists():
                return None
            return out_path.read_bytes()
    except Exception as _exc:
        logger.debug("Rust docx export failed: %s", _exc, exc_info=True)
        return None


def try_rust_import(path: Path) -> str | None:
    if os.environ.get("WA_USE_RUST_ENGINE") != "1":
        return None
    exe = _find_exe("wa_import.exe")
    if exe is None:
        logger.debug("Rust wa_import binary not found")
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
            if result.returncode != 0:
                logger.warning("wa_import exited with %d: %s", result.returncode, result.stderr.strip())
                return None
            if not out_path.exists():
                return None
            return out_path.read_text(encoding="utf-8", errors="replace")
    except Exception as _exc:
        logger.debug("Rust import failed: %s", _exc, exc_info=True)
        return None
