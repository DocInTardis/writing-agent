"""Context Policy Domain module.

Centralizes dynamic context-policy defaults and sanitization for:
- inline-ai context window trimming
- selected-text revision context packaging
"""

from __future__ import annotations

import json
import os


def _clamp_int(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def _coerce_int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except Exception:
        return None


def _safe_int(value: object, default: int, *, lo: int, hi: int) -> int:
    parsed = _coerce_int(value)
    if parsed is None:
        parsed = default
    return _clamp_int(int(parsed), lo, hi)


def _safe_float(value: object, default: float, *, lo: float, hi: float) -> float:
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except Exception:
        parsed = float(default)
    return max(lo, min(hi, parsed))


def _safe_version(value: object) -> str:
    parsed = str(value or "").strip()
    return parsed or "dynamic_v1"


def _load_env_json(env_key: str) -> dict[str, object]:
    raw = str(os.environ.get(env_key, "")).strip()
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _merge_policy_inputs(
    *,
    defaults: dict[str, object],
    raw: object,
    env_override_keys: tuple[str, ...],
) -> dict[str, object]:
    merged = dict(defaults)
    for key in env_override_keys:
        merged.update(_load_env_json(key))
    if isinstance(raw, dict):
        merged.update(raw)
    return merged


def _resolve_primary_or_alias(
    *,
    primary_key: str,
    alias_key: str,
    user_payload: dict[str, object],
    env_mode_payload: dict[str, object],
    env_global_payload: dict[str, object],
    defaults: dict[str, object],
) -> object:
    for source in (user_payload, env_mode_payload, env_global_payload, defaults):
        if primary_key in source:
            return source.get(primary_key)
        if alias_key in source:
            return source.get(alias_key)
    return None


def _default_policy_version() -> str:
    return _safe_version(os.environ.get("WRITING_AGENT_CONTEXT_POLICY_VERSION", "dynamic_v1"))


def _resolve_revise_context_tokens() -> int:
    env_candidates = [
        os.environ.get("WRITING_AGENT_CONTEXT_PROMPT_TOKENS", ""),
        os.environ.get("WRITING_AGENT_REVISE_CONTEXT_TOKENS", ""),
        os.environ.get("WRITING_AGENT_NUM_CTX", ""),
        os.environ.get("OLLAMA_NUM_CTX", ""),
    ]
    for raw in env_candidates:
        parsed = _coerce_int(raw)
        if parsed is not None and parsed > 0:
            return int(parsed)
    return 8192


def normalize_inline_context_policy(raw: object) -> dict[str, object]:
    user_payload = raw if isinstance(raw, dict) else {}
    env_global_payload = _load_env_json("WRITING_AGENT_CONTEXT_POLICY_DEFAULTS_JSON")
    env_mode_payload = _load_env_json("WRITING_AGENT_CONTEXT_POLICY_INLINE_DEFAULTS_JSON")
    defaults = {
        "version": _default_policy_version(),
        "window_formula_base": 220,
        "window_formula_coef": 0.8,
        "short_selection_extra_chars": 180,
        "window_min_chars": 240,
        "window_max_chars": 1200,
        "short_selection_threshold_chars": 60,
        "context_total_max_chars": 2400,
    }
    payload = _merge_policy_inputs(
        defaults=defaults,
        raw=raw,
        env_override_keys=(
            "WRITING_AGENT_CONTEXT_POLICY_DEFAULTS_JSON",
            "WRITING_AGENT_CONTEXT_POLICY_INLINE_DEFAULTS_JSON",
        ),
    )
    extra_chars_source = _resolve_primary_or_alias(
        primary_key="short_selection_extra_chars",
        alias_key="short_boost_chars",
        user_payload=user_payload,
        env_mode_payload=env_mode_payload,
        env_global_payload=env_global_payload,
        defaults=defaults,
    )
    win_min = _safe_int(payload.get("window_min_chars"), 240, lo=80, hi=2000)
    win_max = max(win_min, _safe_int(payload.get("window_max_chars"), 1200, lo=120, hi=4000))
    return {
        "version": _safe_version(payload.get("version")),
        "window_formula_base": _safe_int(payload.get("window_formula_base"), 220, lo=80, hi=1200),
        "window_formula_coef": _safe_float(payload.get("window_formula_coef"), 0.8, lo=0.1, hi=2.0),
        "short_selection_extra_chars": _safe_int(extra_chars_source, 180, lo=0, hi=1200),
        "window_min_chars": win_min,
        "window_max_chars": win_max,
        "short_selection_threshold_chars": _safe_int(
            payload.get("short_selection_threshold_chars"),
            60,
            lo=0,
            hi=1000,
        ),
        "context_total_max_chars": _safe_int(payload.get("context_total_max_chars"), 2400, lo=240, hi=12000),
    }


def normalize_selected_revision_context_policy(raw: object) -> dict[str, object]:
    user_payload = raw if isinstance(raw, dict) else {}
    env_global_payload = _load_env_json("WRITING_AGENT_CONTEXT_POLICY_DEFAULTS_JSON")
    env_mode_payload = _load_env_json("WRITING_AGENT_CONTEXT_POLICY_REVISION_DEFAULTS_JSON")
    defaults = {
        "version": _default_policy_version(),
        "short_selection_threshold_chars": 30,
        "short_selection_threshold_tokens": 8,
        "window_formula_base": 220,
        "window_formula_coef": 0.8,
        "short_boost_chars": 180,
        "short_boost_threshold_chars": 60,
        "window_min_chars": 240,
        "window_max_chars": 1200,
        "min_window_after_trim_chars": 120,
        "prompt_budget_ratio": 0.3,
        "prompt_context_tokens": _resolve_revise_context_tokens(),
    }
    payload = _merge_policy_inputs(
        defaults=defaults,
        raw=raw,
        env_override_keys=(
            "WRITING_AGENT_CONTEXT_POLICY_DEFAULTS_JSON",
            "WRITING_AGENT_CONTEXT_POLICY_REVISION_DEFAULTS_JSON",
        ),
    )
    short_boost_chars_source = _resolve_primary_or_alias(
        primary_key="short_boost_chars",
        alias_key="short_selection_extra_chars",
        user_payload=user_payload,
        env_mode_payload=env_mode_payload,
        env_global_payload=env_global_payload,
        defaults=defaults,
    )
    short_boost_threshold_source = _resolve_primary_or_alias(
        primary_key="short_boost_threshold_chars",
        alias_key="short_selection_threshold_chars",
        user_payload=user_payload,
        env_mode_payload=env_mode_payload,
        env_global_payload=env_global_payload,
        defaults=defaults,
    )
    win_min = _safe_int(payload.get("window_min_chars"), 240, lo=40, hi=2000)
    win_max = max(win_min, _safe_int(payload.get("window_max_chars"), 1200, lo=80, hi=5000))
    return {
        "version": _safe_version(payload.get("version")),
        "short_selection_threshold_chars": _safe_int(
            payload.get("short_selection_threshold_chars"),
            30,
            lo=8,
            hi=400,
        ),
        "short_selection_threshold_tokens": _safe_int(
            payload.get("short_selection_threshold_tokens"),
            8,
            lo=4,
            hi=200,
        ),
        "window_formula_base": _safe_int(
            payload.get("window_formula_base"),
            220,
            lo=80,
            hi=1200,
        ),
        "window_formula_coef": _safe_float(
            payload.get("window_formula_coef"),
            0.8,
            lo=0.2,
            hi=2.5,
        ),
        "short_boost_chars": _safe_int(
            short_boost_chars_source,
            180,
            lo=0,
            hi=1200,
        ),
        "short_boost_threshold_chars": _safe_int(
            short_boost_threshold_source,
            60,
            lo=8,
            hi=500,
        ),
        "window_min_chars": win_min,
        "window_max_chars": win_max,
        "min_window_after_trim_chars": _safe_int(
            payload.get("min_window_after_trim_chars"),
            120,
            lo=0,
            hi=1200,
        ),
        "prompt_budget_ratio": _safe_float(
            payload.get("prompt_budget_ratio"),
            0.3,
            lo=0.05,
            hi=0.8,
        ),
        "prompt_context_tokens": _safe_int(
            payload.get("prompt_context_tokens"),
            _resolve_revise_context_tokens(),
            lo=512,
            hi=131072,
        ),
    }
