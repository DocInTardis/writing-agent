"""Generation policy capability helpers."""

from __future__ import annotations


def system_pressure_high(*, os_module, psutil_module=None) -> bool:
    raw_cpu = os_module.environ.get("WRITING_AGENT_FAST_CPU", "").strip()
    raw_mem = os_module.environ.get("WRITING_AGENT_FAST_MEM", "").strip()
    try:
        cpu_threshold = float(raw_cpu) if raw_cpu else 85.0
    except Exception:
        cpu_threshold = 85.0
    try:
        mem_threshold = float(raw_mem) if raw_mem else 85.0
    except Exception:
        mem_threshold = 85.0
    if psutil_module is None:
        try:
            import psutil as psutil_module  # type: ignore
        except Exception:
            return False
    try:
        cpu = psutil_module.cpu_percent(interval=0.2)
        mem = psutil_module.virtual_memory().percent
    except Exception:
        return False
    return cpu >= cpu_threshold or mem >= mem_threshold


def should_use_fast_generate(*, raw_instruction: str, target_chars: int, prefs: dict | None, os_module, system_pressure_high_fn) -> bool:
    _ = raw_instruction, target_chars
    prefs = prefs or {}
    if str(os_module.environ.get("WRITING_AGENT_FAST_GENERATE", "")).strip().lower() in {"1", "true", "yes", "on"}:
        return True
    if prefs.get("fast_generate") is True:
        return True
    return system_pressure_high_fn()


def summarize_analysis(*, raw: str, analysis: dict) -> dict:
    if not isinstance(analysis, dict):
        return {"summary": "", "missing": [], "steps": []}
    intent = analysis.get("intent") or {}
    entities = analysis.get("entities") or {}
    missing = analysis.get("missing") or []
    constraints = analysis.get("constraints") or []
    decomposition = analysis.get("decomposition") or analysis.get("steps") or []
    parts: list[str] = []
    if raw:
        parts.append(f"requirement: {raw}")
    name = str(intent.get("name") or "").strip()
    if name:
        parts.append(f"intent: {name}")
    for key in ("title", "purpose", "length", "formatting", "audience", "output_form", "voice", "avoid", "scope"):
        value = str(entities.get(key) or "").strip()
        if value:
            parts.append(f"{key}: {value}")
    if constraints:
        parts.append("constraints: " + "; ".join([str(item) for item in constraints if str(item).strip()]))
    steps: list[str] = []
    if isinstance(decomposition, list):
        steps.extend([str(item).strip() for item in decomposition if str(item).strip()])
    if not steps and constraints:
        steps.extend([f"constraint: {str(item).strip()}" for item in constraints if str(item).strip()])
    return {
        "summary": " | ".join([part for part in parts if part]),
        "missing": missing,
        "steps": steps[:6],
    }


__all__ = [name for name in globals() if not name.startswith("__")]
