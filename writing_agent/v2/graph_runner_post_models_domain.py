"""Model selection and memory helpers split from graph_runner_post_domain.py."""

from __future__ import annotations

import ctypes
import subprocess

def _default_worker_models(*, preferred: str) -> list[str]:
    installed = _ollama_installed_models()
    if not installed:
        return [preferred]
    out: list[str] = []
    if preferred in installed and not _looks_like_embedding_model(preferred):
        out.append(preferred)
    # Add other non-embedding models as fallback candidates.
    for m in sorted(installed):
        if m == preferred:
            continue
        if _looks_like_embedding_model(m):
            continue
        out.append(m)
    return out or [preferred]

def _looks_like_embedding_model(name: str) -> bool:
    n = (name or "").lower()
    return any(k in n for k in ["embed", "embedding", "bge-", "e5-", "nomic-embed"])

def _ollama_installed_models() -> set[str]:
    try:
        p = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=8)
        if p.returncode != 0:
            return set()
        lines = (p.stdout or "").splitlines()
        out: set[str] = set()
        for line in lines[1:]:
            parts = line.split()
            if parts:
                out.add(parts[0].strip())
        return out
    except Exception:
        return set()

def _ollama_model_sizes_gb() -> dict[str, float]:
    # Parse `ollama list` SIZE column; best-effort.
    try:
        p = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=8)
        if p.returncode != 0:
            return {}
        out: dict[str, float] = {}
        for line in (p.stdout or "").splitlines()[1:]:
            parts = line.split()
            if len(parts) < 3:
                continue
            name = parts[0].strip()
            # SIZE is usually the 3rd column, e.g. "4.1" "GB"
            try:
                num = float(parts[2])
                unit = parts[3].upper() if len(parts) > 3 else "GB"
                if unit.startswith("MB"):
                    gb = num / 1024.0
                elif unit.startswith("KB"):
                    gb = num / (1024.0 * 1024.0)
                else:
                    gb = num
                out[name] = max(0.1, gb)
            except Exception:
                continue
        return out
    except Exception:
        return {}

def _get_memory_bytes() -> tuple[int, int]:
    # Windows GlobalMemoryStatusEx; fallback returns (0,0)
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    try:
        st = MEMORYSTATUSEX()
        st.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):  # type: ignore[attr-defined]
            return int(st.ullTotalPhys), int(st.ullAvailPhys)
    except Exception:
        pass
    return 0, 0


__all__ = [name for name in globals() if not name.startswith("__")]
