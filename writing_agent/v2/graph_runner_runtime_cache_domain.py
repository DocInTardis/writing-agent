"""Runtime JSON cache and cached-section helpers extracted from graph_runner_runtime_common_domain."""

from __future__ import annotations

import json
import os
import re

from writing_agent.llm.providers._sse import repair_utf8_mojibake


def _base():
    from writing_agent.v2 import graph_runner_runtime_common_domain as base

    return base


def _runtime_json_cache_enabled() -> bool:
    if "WRITING_AGENT_RUNTIME_JSON_CACHE" in os.environ:
        return _base()._env_flag("WRITING_AGENT_RUNTIME_JSON_CACHE", "0")
    return _base()._env_flag("WRITING_AGENT_ENABLE_RUNTIME_JSON_CACHE", "1")


def _default_evidence_pack(*, is_starved: bool = False, stub_mode: bool = False, reasons: list[str] | None = None) -> dict:
    return {"summary": "", "sources": [], "allowed_urls": [], "data_starvation": {"is_starved": bool(is_starved), "stub_mode": bool(stub_mode), "reasons": list(reasons or [])}, "facts": [], "fact_gain_count": 0, "fact_density_score": 0.0, "online_hits": 0}


def _normalize_evidence_pack(payload: object) -> dict:
    if not isinstance(payload, dict):
        return _default_evidence_pack()
    out = _default_evidence_pack()
    out.update({k: v for k, v in payload.items() if k in out or k == "data_starvation"})
    out["sources"] = [dict(x) for x in (payload.get("sources") or []) if isinstance(x, dict)]
    out["allowed_urls"] = [str(x).strip() for x in (payload.get("allowed_urls") or []) if str(x).strip()]
    out["facts"] = [dict(x) for x in (payload.get("facts") or []) if isinstance(x, dict)]
    if not isinstance(out.get("data_starvation"), dict):
        out["data_starvation"] = {"is_starved": False, "stub_mode": False, "reasons": []}
    return out


def _runtime_evidence_cache_key(*, provider_name: str, model: str, instruction: str, section: str, analysis: dict | None, plan) -> str:
    return json.dumps([
        str(provider_name or ""),
        str(model or ""),
        str(instruction or ""),
        str(section or ""),
        dict(analysis or {}),
        _serialize_plan_map({"section": plan}).get("section") if plan is not None else None,
    ], ensure_ascii=False, sort_keys=True)


def _runtime_json_cache_key(local_cache, namespace: str, *parts: object) -> str:
    safe_parts = [str(namespace or "").strip()]
    safe_parts.extend(json.dumps(part, ensure_ascii=False, sort_keys=True) if isinstance(part, (dict, list, tuple, set)) else str(part) for part in parts)
    return local_cache._make_key(*safe_parts)


def _runtime_json_cache_get(local_cache, key: str) -> dict | list | None:
    if not _runtime_json_cache_enabled():
        return None
    try:
        raw = local_cache.get(key)
        return json.loads(raw) if raw else None
    except Exception:
        return None


def _runtime_json_cache_put(local_cache, key: str, payload: dict | list, *, metadata: dict | None = None) -> None:
    if not _runtime_json_cache_enabled():
        return
    try:
        local_cache.put(key, json.dumps(payload, ensure_ascii=False), metadata=metadata or {})
    except Exception:
        pass


def _load_evidence_pack_cached(*, local_cache, cache_lock, provider_name: str, model: str, instruction: str, section: str, analysis: dict | None, plan, base_url: str):
    cache_key = _runtime_json_cache_key(local_cache, "evidence_pack_v1", provider_name, model, instruction, section, analysis or {}, _serialize_plan_map({section: plan}))
    with cache_lock:
        cached_payload = _runtime_json_cache_get(local_cache, cache_key)
    if isinstance(cached_payload, dict):
        return _normalize_evidence_pack(cached_payload), True
    payload = _base()._build_evidence_pack(instruction=instruction, section=section, analysis=analysis, plan=plan, base_url=base_url, model=model)
    normalized = _normalize_evidence_pack(payload)
    with cache_lock:
        _runtime_json_cache_put(local_cache, cache_key, normalized, metadata={"type": "evidence_pack", "provider": provider_name, "model": model})
    return normalized, False


def _is_keywords_section_runtime(section_title: str) -> bool:
    normalized = re.sub(r"[\s:：;；,，、/|]+", "", str(section_title or "").strip().lower())
    return normalized in {"关键词", "关键字", "keywords"}


def _section_cache_min_chars(section_title: str) -> int:
    return 0 if _is_keywords_section_runtime(section_title) else 120


def _count_runtime_cjk(text: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fff]", str(text or "")))


def _count_runtime_latin1_noise(text: str) -> int:
    return len(re.findall(r"[\x80-\xff]", str(text or "")))


def _repair_mixed_cached_mojibake(text: str) -> str:
    source = str(text or "")
    repaired = repair_utf8_mojibake(source)
    if str(repaired or "").strip() and repaired != source:
        return repaired

    def _repair_fragment(match: re.Match[str]) -> str:
        fragment = match.group(0)
        fixed = repair_utf8_mojibake(fragment)
        return fixed if str(fixed or "").strip() else fragment

    return re.sub(r"[\x80-\xff]{2,}", _repair_fragment, source)


def _decode_cache_literal_escapes(text: str) -> str:
    candidate = str(text or "")
    if "\\" not in candidate:
        return candidate

    candidate = re.sub(
        r"\\x([0-9a-fA-F]{2})",
        lambda m: chr(int(m.group(1), 16)),
        candidate,
    )
    candidate = re.sub(
        r"\\u([0-9a-fA-F]{4})",
        lambda m: chr(int(m.group(1), 16)),
        candidate,
    )
    candidate = candidate.replace(r"\n", "\n").replace(r"\t", "\t")
    return candidate


def _normalize_cached_keywords(candidate: str) -> str:
    text = str(candidate or "")
    text = _repair_mixed_cached_mojibake(_decode_cache_literal_escapes(text))
    text = re.sub(r"\[\d+\]", " ", text)
    text = re.sub(r"\(\d+\)", " ", text)
    text = re.sub(r"[?；;,，、/|]+", "；", text)
    text = re.sub(r"\s+", " ", text).strip(" ；")

    label_match = re.match(r"^(关键词|关键字|keywords)\s*[:：]?\s*(.*)$", text, flags=re.IGNORECASE)
    if label_match:
        values = [part.strip() for part in re.split(r"[；]+", label_match.group(2) or "") if part.strip()]
        return f"关键词：{'；'.join(values)}" if values else "关键词："

    return text.strip()


def _sanitize_cached_section_text(*, section_title: str, text: str) -> str:
    cleaned = str(text or "")
    if _is_keywords_section_runtime(section_title):
        cleaned = _normalize_cached_keywords(cleaned)
    return cleaned.strip()


def _usable_cached_section_text(section_title: str, text: str) -> str:
    cleaned = _sanitize_cached_section_text(section_title=section_title, text=text)
    if not cleaned:
        return ""
    if _base()._is_reference_section(section_title):
        return ""
    min_chars = _section_cache_min_chars(section_title)
    return cleaned if len(cleaned) >= min_chars else ""


def _prime_cached_sections(*, sections: list[str], targets: dict[str, object], instruction: str, local_cache, cache_lock) -> dict[str, str]:
    hits: dict[str, str] = {}
    with cache_lock:
        for sec in sections:
            sec_title = _base()._section_title(sec) or sec
            if _base()._is_reference_section(sec_title):
                continue
            sec_target = targets.get(sec)
            min_chars = int(getattr(sec_target, "min_chars", 0) or 0) if sec_target else 0
            cached = local_cache.get_section(sec_title, instruction, min_chars)
            cleaned = _usable_cached_section_text(sec_title, cached)
            if cleaned:
                hits[sec] = cleaned
    return hits


def _serialize_plan_map(plan_map: dict[str, object]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for key, plan in (plan_map or {}).items():
        if plan is None:
            continue
        out[str(key)] = {
            "title": plan.title,
            "target_chars": int(plan.target_chars or 0),
            "min_chars": int(plan.min_chars or 0),
            "max_chars": int(plan.max_chars or 0),
            "min_tables": int(plan.min_tables or 0),
            "min_figures": int(plan.min_figures or 0),
            "key_points": list(plan.key_points or []),
            "figures": list(plan.figures or []),
            "tables": list(plan.tables or []),
            "evidence_queries": list(plan.evidence_queries or []),
        }
    return out


def _deserialize_plan_map(payload: object) -> dict[str, object]:
    out: dict[str, object] = {}
    if not isinstance(payload, dict):
        return out
    plan_type = _base().PlanSection
    for key, row in payload.items():
        if not isinstance(row, dict):
            continue
        out[str(key)] = plan_type(
            title=str(row.get("title") or key),
            target_chars=int(row.get("target_chars") or 0),
            min_chars=int(row.get("min_chars") or 0),
            max_chars=int(row.get("max_chars") or 0),
            min_tables=int(row.get("min_tables") or 0),
            min_figures=int(row.get("min_figures") or 0),
            key_points=[str(x).strip() for x in (row.get("key_points") or []) if str(x).strip()],
            figures=[dict(x) for x in (row.get("figures") or []) if isinstance(x, dict)],
            tables=[dict(x) for x in (row.get("tables") or []) if isinstance(x, dict)],
            evidence_queries=[str(x).strip() for x in (row.get("evidence_queries") or []) if str(x).strip()],
        )
    return out


__all__ = [name for name in globals() if not name.startswith("__")]
