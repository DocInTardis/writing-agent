"""Common runtime helpers used by the split runtime wrapper."""

from __future__ import annotations

import json
import os
import queue
import re
import threading
import time

from writing_agent.llm.factory import get_default_provider
from writing_agent.llm.providers._sse import repair_utf8_mojibake
from writing_agent.v2.global_config import FAILURE_API_PROVIDER_UNREACHABLE, classify_provider_error
from writing_agent.v2.graph_runner import *  # noqa: F401,F403
from writing_agent.v2 import graph_runner as _graph_runner_module

for _name in dir(_graph_runner_module):
    if _name.startswith("__"):
        continue
    if _name not in globals():
        globals()[_name] = getattr(_graph_runner_module, _name)


def _env_flag(name: str, default: str = "0") -> bool:
    return str(os.environ.get(name, default)).strip().lower() in {"1", "true", "yes", "on"}


def _runtime_escape_prompt_text(raw: object) -> str:
    text = str(raw or "")
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


_REFERENCE_QUERY_HEADING_STOPWORDS = {
    "摘要",
    "关键词",
    "关键字",
    "引言",
    "需求分析",
    "系统总体架构",
    "核心业务流程",
    "关键技术实现",
    "实验结果与分析",
    "实验设计与结果",
    "系统设计与实现",
    "结论",
    "参考文献",
}


def _derive_reference_query(*, analysis: dict | None, analysis_summary: str, instruction: str) -> str:
    parts: list[str] = []
    seen: set[str] = set()

    def _push(raw: str) -> bool:
        cleaned = graph_reference_domain.normalize_reference_query(str(raw or ""))
        if not cleaned or cleaned in _REFERENCE_QUERY_HEADING_STOPWORDS:
            return False
        if cleaned in seen:
            return False
        seen.add(cleaned)
        parts.append(cleaned)
        return True

    title_hint = graph_reference_domain.normalize_reference_query(_guess_title(instruction) or "")
    if title_hint:
        return title_hint
    topic = graph_reference_domain.normalize_reference_query(str((analysis or {}).get("topic") or ""))
    if topic:
        _push(topic)
        for raw in ((analysis or {}).get("keywords") or []):
            cleaned = graph_reference_domain.normalize_reference_query(str(raw or ""))
            if not cleaned or cleaned in _REFERENCE_QUERY_HEADING_STOPWORDS:
                continue
            if cleaned in topic or topic in cleaned:
                _push(cleaned)
                continue
            if len(parts) < 4:
                _push(cleaned)
        if parts:
            return " ".join(parts[:6]).strip()
    for fallback in (instruction, analysis_summary):
        cleaned = graph_reference_domain.normalize_reference_query(str(fallback or ""))
        if cleaned:
            return cleaned
    return ""


def _should_synthesize_analysis(*, instruction: str, current_text: str, required_outline, required_h2) -> bool:
    if str(current_text or "").strip():
        return False
    if not (required_outline or required_h2):
        return False
    return _resolve_doc_type_for_prompt(instruction) in {"academic", "paper", "thesis", "report", "weekly"}


def _synthesize_topic_and_keywords(instruction: str) -> tuple[str, list[str]]:
    raw_instruction = str(instruction or "").strip()
    title_hint = str(_guess_title(raw_instruction) or "").strip()
    normalized_title = graph_reference_domain.normalize_reference_query(title_hint)
    normalized_instruction = graph_reference_domain.normalize_reference_query(raw_instruction)
    topic = title_hint or normalized_title or normalized_instruction or raw_instruction
    keyword_source = normalized_title or normalized_instruction or title_hint or raw_instruction
    return str(topic or "").strip(), _topic_tokens(keyword_source)[:8]


def _synthesize_analysis_from_requirements(*, instruction: str, required_outline, required_h2) -> dict:
    must_include: list[str] = []
    for _lvl, title in (required_outline or []):
        clean = _clean_outline_title(title)
        if clean:
            must_include.append(clean)
    for title in (required_h2 or []):
        clean = _clean_outline_title(title)
        if clean:
            must_include.append(clean)
    must_include = _dedupe_keep_order(must_include)
    topic, keywords = _synthesize_topic_and_keywords(instruction)
    base = {"topic": topic, "doc_type": _resolve_doc_type_for_prompt(instruction), "keywords": keywords, "must_include": must_include, "constraints": [], "audience": "", "style": "formal", "_synthesized": True}
    return _normalize_analysis_for_generation(base, instruction)


_WEEKLY_FAST_PLAN_SECTIONS = ["本周工作", "问题与风险", "下周计划", "需协助事项"]
_ACADEMIC_FAST_PLAN_SECTIONS = ["摘要", "关键词", "引言", "系统设计与实现", "实验与结果分析", "结论", "参考文献"]


def _plan_detail_skip_decision() -> tuple[bool, str]:
    requested = _env_flag("WRITING_AGENT_SKIP_PLAN_DETAIL", "0")
    if not requested:
        return False, ""
    profile = str(os.environ.get("WRITING_AGENT_RUNTIME_PROFILE", "")).strip().lower()
    allowed = _env_flag("WRITING_AGENT_ALLOW_SKIP_PLAN_DETAIL", "0")
    if (not allowed) and profile in {"smoke", "dev", "test"}:
        allowed = True
    return (True, "env_skip_plan_detail") if allowed else (False, "skip_plan_detail_ignored")


def _should_skip_plan_detail() -> bool:
    decision, _ = _plan_detail_skip_decision()
    return decision


def _fast_plan_sections_for_instruction(instruction: str) -> list[str]:
    default_sections = [str(x).strip() for x in (_default_outline_from_instruction(instruction) or []) if str(x).strip()]
    if _resolve_doc_type_for_prompt(instruction) == "weekly":
        return default_sections or list(_WEEKLY_FAST_PLAN_SECTIONS)
    weekly_tokens = {"this week work", "next week plan", "support needed", "本周工作", "下周计划", "需协助事项"}
    filtered = [x for x in default_sections if x.lower() not in weekly_tokens]
    return filtered or list(_ACADEMIC_FAST_PLAN_SECTIONS)


def _validate_plan_detail(*, instruction: str, sections: list[str], plan_map: dict) -> tuple[bool, list[str], dict]:
    reasons: list[str] = []
    detail_rows: list[dict] = []
    evidence_total = 0
    if _resolve_doc_type_for_prompt(instruction) != "academic":
        return True, reasons, {"doc_type": _resolve_doc_type_for_prompt(instruction)}
    method_or_experiment_without_media: list[str] = []
    for sec in sections:
        title = _section_title(sec) or sec
        if _is_reference_section(title):
            continue
        plan = plan_map.get(sec)
        if not plan:
            reasons.append("plan_detail_missing_section")
            continue
        key_points = [str(x).strip() for x in (getattr(plan, "key_points", []) or []) if str(x).strip()]
        evidence_queries = [str(x).strip() for x in (getattr(plan, "evidence_queries", []) or []) if str(x).strip()]
        tables = list(getattr(plan, "tables", []) or [])
        figures = list(getattr(plan, "figures", []) or [])
        evidence_total += len(evidence_queries)
        detail_rows.append({"title": title, "key_points": len(key_points), "evidence_queries": len(evidence_queries), "tables": len(tables), "figures": len(figures)})
        if len(key_points) < 2:
            reasons.append(f"plan_detail_key_points_insufficient:{title}")
        if len(evidence_queries) < 2:
            reasons.append("plan_detail_evidence_queries_insufficient")
        lowered = str(title or "").lower()
        if any(token in lowered for token in ("method", "experiment", "result", "分析", "方法", "实验", "设计")) and (not tables) and (not figures):
            method_or_experiment_without_media.append(title)
    if method_or_experiment_without_media:
        reasons.extend([f"plan_detail_method_or_experiment_missing_media:{title}" for title in method_or_experiment_without_media])
    meta = {"rows": detail_rows[:20], "evidence_total": evidence_total}
    return len(reasons) == 0, reasons, meta


def _is_starvation_scored_section(title: object) -> bool:
    text = str(_section_title(str(title or "")) or str(title or "")).strip().lower()
    if not text:
        return False
    if text in {"abstract", "??", "keywords", "???", "???"}:
        return False
    return not _is_reference_section(text)


def _starvation_section_key(raw: object) -> str:
    return str(_section_title(str(raw or "")) or str(raw or "")).strip()


def _starvation_failure_decision(*, sections, data_starvation_rows, evidence_enabled: bool) -> dict[str, object]:
    section_titles = {_starvation_section_key(sec) for sec in (sections or []) if _is_starvation_scored_section(sec)}
    rows = [dict(row) for row in (data_starvation_rows or []) if isinstance(row, dict)]
    starved_titles = {_starvation_section_key(row.get("title") or row.get("section") or "") for row in rows if _is_starvation_scored_section(row.get("title") or row.get("section") or "")}
    total = len(section_titles)
    failed = len([title for title in starved_titles if title in section_titles])
    ratio = round((float(failed) / float(max(1, total))) if evidence_enabled and total else 0.0, 4)
    threshold = max(0.0, min(1.0, float(os.environ.get("WRITING_AGENT_RAG_DATA_STARVATION_FAIL_RATIO", "0.25") or 0.25)))
    triggered = bool(evidence_enabled and total and ratio >= threshold)
    return {"triggered": triggered, "ratio": ratio, "threshold": threshold, "starved_count": failed, "section_count": total, "failure_reason": "insufficient_fact_density" if triggered else "", "rows": rows[:20]}

from writing_agent.v2 import (
    graph_runner_runtime_cache_domain as runtime_cache_domain,
    graph_runner_runtime_provider_domain as runtime_provider_domain,
)


_GENERATION_SLOT_MAP = runtime_provider_domain._GENERATION_SLOT_MAP


def _provider_default_model(provider_name: str) -> str:
    return str(runtime_provider_domain._provider_default_model(provider_name))


def _provider_timeout_s(provider_name: str) -> float:
    return float(runtime_provider_domain._provider_timeout_s(provider_name))


def _provider_default_per_model_concurrency(provider_name: str) -> int:
    return int(runtime_provider_domain._provider_default_per_model_concurrency(provider_name))


def _generation_slot_enabled() -> bool:
    return bool(runtime_provider_domain._generation_slot_enabled())


def _generation_slot_limit(provider_name: str, model: str) -> int:
    return int(runtime_provider_domain._generation_slot_limit(provider_name, model))


def _generation_slot(provider_name: str, model: str):
    return runtime_provider_domain._generation_slot(provider_name, model)


def _call_with_generation_slot(*, provider_name: str, model: str, fn, out_queue: queue.Queue[dict] | None = None, section: str = "", section_id: str = "", stage: str = "section"):
    return runtime_provider_domain._call_with_generation_slot(
        provider_name=provider_name,
        model=model,
        fn=fn,
        out_queue=out_queue,
        section=section,
        section_id=section_id,
        stage=stage,
    )


def _guarded_stream_structured_blocks(*, provider_name: str, model: str, out_queue: queue.Queue[dict], section: str, section_id: str, **kwargs):
    return runtime_provider_domain._guarded_stream_structured_blocks(
        provider_name=provider_name,
        model=model,
        out_queue=out_queue,
        section=section,
        section_id=section_id,
        **kwargs,
    )


def _provider_default_evidence_workers(provider_name: str, *, sections_count: int) -> int:
    return int(runtime_provider_domain._provider_default_evidence_workers(provider_name, sections_count=sections_count))


def _runtime_json_cache_enabled() -> bool:
    return bool(runtime_cache_domain._runtime_json_cache_enabled())


def _default_evidence_pack(*, is_starved: bool = False, stub_mode: bool = False, reasons: list[str] | None = None) -> dict:
    return dict(runtime_cache_domain._default_evidence_pack(is_starved=is_starved, stub_mode=stub_mode, reasons=reasons))


def _normalize_evidence_pack(payload: object) -> dict:
    return dict(runtime_cache_domain._normalize_evidence_pack(payload))


def _runtime_evidence_cache_key(*, provider_name: str, model: str, instruction: str, section: str, analysis: dict | None, plan) -> str:
    return str(runtime_cache_domain._runtime_evidence_cache_key(provider_name=provider_name, model=model, instruction=instruction, section=section, analysis=analysis, plan=plan))


def _runtime_json_cache_key(local_cache, namespace: str, *parts: object) -> str:
    return str(runtime_cache_domain._runtime_json_cache_key(local_cache, namespace, *parts))


def _runtime_json_cache_get(local_cache, key: str) -> dict | list | None:
    return runtime_cache_domain._runtime_json_cache_get(local_cache, key)


def _runtime_json_cache_put(local_cache, key: str, payload: dict | list, *, metadata: dict | None = None) -> None:
    runtime_cache_domain._runtime_json_cache_put(local_cache, key, payload, metadata=metadata)


def _load_evidence_pack_cached(*, local_cache, cache_lock, provider_name: str, model: str, instruction: str, section: str, analysis: dict | None, plan, base_url: str):
    return runtime_cache_domain._load_evidence_pack_cached(local_cache=local_cache, cache_lock=cache_lock, provider_name=provider_name, model=model, instruction=instruction, section=section, analysis=analysis, plan=plan, base_url=base_url)


def _is_keywords_section_runtime(section_title: str) -> bool:
    return bool(runtime_cache_domain._is_keywords_section_runtime(section_title))


def _section_cache_min_chars(section_title: str) -> int:
    return int(runtime_cache_domain._section_cache_min_chars(section_title))


def _count_runtime_cjk(text: str) -> int:
    return int(runtime_cache_domain._count_runtime_cjk(text))


def _count_runtime_latin1_noise(text: str) -> int:
    return int(runtime_cache_domain._count_runtime_latin1_noise(text))


def _repair_mixed_cached_mojibake(text: str) -> str:
    return str(runtime_cache_domain._repair_mixed_cached_mojibake(text))


def _decode_cache_literal_escapes(text: str) -> str:
    return str(runtime_cache_domain._decode_cache_literal_escapes(text))


def _normalize_cached_keywords(candidate: str) -> str:
    return str(runtime_cache_domain._normalize_cached_keywords(candidate))


def _sanitize_cached_section_text(*, section_title: str, text: str) -> str:
    return str(runtime_cache_domain._sanitize_cached_section_text(section_title=section_title, text=text))


def _usable_cached_section_text(section_title: str, text: str) -> str:
    return str(runtime_cache_domain._usable_cached_section_text(section_title, text))


def _prime_cached_sections(*, sections: list[str], targets: dict[str, SectionTargets], instruction: str, local_cache, cache_lock) -> dict[str, str]:
    return dict(runtime_cache_domain._prime_cached_sections(sections=sections, targets=targets, instruction=instruction, local_cache=local_cache, cache_lock=cache_lock))


def _serialize_plan_map(plan_map: dict[str, PlanSection]) -> dict[str, dict]:
    return dict(runtime_cache_domain._serialize_plan_map(plan_map))


def _deserialize_plan_map(payload: object) -> dict[str, PlanSection]:
    return dict(runtime_cache_domain._deserialize_plan_map(payload))


def _provider_preflight(*, provider, model: str, provider_name: str) -> tuple[bool, str]:
    ok, reason = runtime_provider_domain._provider_preflight(provider=provider, model=model, provider_name=provider_name)
    return bool(ok), str(reason or "")


__all__ = [name for name in globals() if not name.startswith("__")]
