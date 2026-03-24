"""Thin runtime orchestration built on split helper domains."""

from __future__ import annotations

import os
import queue
import threading
import time
from pathlib import Path
from writing_agent.v2.global_config import FAILURE_API_PROVIDER_UNREACHABLE, FAILURE_PROVIDER_DISABLED, classify_provider_error
from writing_agent.v2.graph_runner import *  # noqa: F401,F403
from writing_agent.v2.document_assembly import assemble_by_id_map, find_missing_sections
from writing_agent.v2.section_spec import build_section_specs, token_to_id_map
from writing_agent.v2 import graph_reference_domain
from writing_agent.v2 import graph_runner_evidence_domain as evidence_domain
from writing_agent.v2 import graph_runner_runtime_provider_domain as provider_domain
from writing_agent.v2.graph_runner_runtime_originality_domain import (
    OriginalityTracker,
    build_feedback,
    collect_source_rows,
    evaluate_hot_sample,
    rewrite_for_originality,
)
from writing_agent.v2 import graph_runner_runtime_finalize_domain as finalize_domain
from writing_agent.v2 import graph_runner_runtime_analysis_domain as analysis_domain
from writing_agent.v2 import graph_runner_runtime_plan_domain as plan_domain


def _env_flag(name: str, default: str = "0") -> bool:
    return str(os.environ.get(name, default)).strip().lower() in {"1", "true", "yes", "on"}


def _flush_trace(rows: list[dict]):
    while rows:
        row = rows.pop(0)
        yield {"event": "prompt_route", "stage": row.get("stage", ""), "metadata": row.get("metadata", {})}


def _drain_queue(local_q: queue.Queue[dict]):
    while True:
        try:
            yield local_q.get_nowait()
        except queue.Empty:
            break


def _format_reference_items(sources: list[dict]) -> list[str]:
    return graph_reference_domain.format_reference_items(
        sources or [],
        extract_year_fn=graph_reference_domain.extract_year,
        format_authors_fn=graph_reference_domain.format_authors,
    )


def run_generate_graph_impl(
    runtime_api,
    *,
    instruction: str,
    current_text: str,
    required_h2: list[str] | None,
    required_outline: list[tuple[int, str]] | None = None,
    expand_outline: bool = False,
    config: GenerateConfig,
):
    provider_name = runtime_api.get_provider_name()
    provider_snapshot = runtime_api.get_provider_snapshot()
    strict_json = _env_flag("WRITING_AGENT_STRICT_JSON", "1")
    run_id = f"run_{int(time.time() * 1000)}"
    run_start_ts = time.time()
    prompt_trace: list[dict] = []
    prompt_events: list[dict] = []

    def _capture_prompt_trace(row: dict) -> None:
        finalize_domain.capture_prompt_trace(prompt_trace, prompt_events, row)

    def _build_final_event(*, text: str, problems: list[str], status: str, failure_reason: str, quality_snapshot: dict | None = None, runtime_status: str = "", runtime_failure_reason: str = "", quality_passed: bool | None = None, quality_failure_reason: str = "", extra_fields: dict | None = None) -> dict:
        return finalize_domain.build_final_event(
            provider_snapshot=provider_snapshot,
            text=text,
            problems=problems,
            status=status,
            failure_reason=failure_reason,
            quality_snapshot=quality_snapshot,
            runtime_status=runtime_status,
            runtime_failure_reason=runtime_failure_reason,
            quality_passed=quality_passed,
            quality_failure_reason=quality_failure_reason,
            extra_fields=extra_fields,
        )

    settings, installed = provider_domain.resolve_provider_settings(
        runtime_api=runtime_api,
        provider_name=provider_name,
        provider_snapshot=provider_snapshot,
    )
    if provider_name == "ollama" and not settings.enabled:
        reason = FAILURE_PROVIDER_DISABLED
        yield _build_final_event(text="", problems=[reason], status="failed", failure_reason=reason, quality_snapshot={"provider": provider_snapshot}, runtime_status="failed", runtime_failure_reason=reason, quality_passed=False, quality_failure_reason=reason)
        return

    preflight_model = provider_domain.select_preflight_model(config=config, settings=settings)
    try:
        preflight_provider = provider_domain.create_preflight_provider(
            runtime_api=runtime_api,
            provider_name=provider_name,
            settings=settings,
            preflight_model=preflight_model,
            run_id=run_id,
        )
    except Exception as exc:
        reason = classify_provider_error(str(exc))
        yield _build_final_event(text="", problems=[reason], status="failed", failure_reason=reason, quality_snapshot={"provider": provider_snapshot, "error": str(exc)[:240]}, runtime_status="failed", runtime_failure_reason=reason, quality_passed=False, quality_failure_reason=reason)
        return
    preflight_ok, preflight_reason = runtime_api._provider_preflight(provider=preflight_provider, model=preflight_model, provider_name=provider_name)
    if not preflight_ok:
        reason = preflight_reason or FAILURE_API_PROVIDER_UNREACHABLE
        yield _build_final_event(text="", problems=[reason], status="failed", failure_reason=reason, quality_snapshot={"provider": provider_snapshot}, runtime_status="failed", runtime_failure_reason=reason, quality_passed=False, quality_failure_reason=reason)
        return

    agg_model, worker_models, main_model, support_model = provider_domain.resolve_runtime_models(
        runtime_api=runtime_api,
        provider_name=provider_name,
        settings=settings,
        installed=installed,
        config=config,
    )

    data_dir = Path(os.environ.get("WRITING_AGENT_DATA_DIR", str(Path(__file__).resolve().parents[2] / ".data"))).resolve()
    local_cache = runtime_api.LocalCache(data_dir / "cache")
    text_store = runtime_api.TextStore(data_dir / "text_store")
    cache_io_lock = threading.Lock()

    runtime_api._record_phase_timing(run_id, {"phase": "PLAN", "event": "start"})
    yield {"event": "state", "name": "PLAN", "phase": "start"}
    analysis_state = yield from analysis_domain.resolve_analysis_state(
        runtime_api=runtime_api,
        instruction=instruction,
        current_text=current_text,
        required_h2=required_h2,
        required_outline=required_outline,
        local_cache=local_cache,
        provider_name=provider_name,
        settings=settings,
        agg_model=agg_model,
        run_id=run_id,
        capture_prompt_trace=_capture_prompt_trace,
        prompt_events=prompt_events,
        build_final_event=_build_final_event,
    )
    if analysis_state is None:
        return
    analysis = dict(analysis_state.get("analysis") or {})
    analysis_summary = str(analysis_state.get("analysis_summary") or "")
    writer_requirement = str(analysis_state.get("writer_requirement") or "")
    paradigm_decision = dict(analysis_state.get("paradigm_decision") or {})
    forced_sections = [str(x).strip() for x in (analysis_state.get("forced_sections") or []) if str(x).strip()]

    plan_state = yield from plan_domain.resolve_section_plan_state(
        runtime_api=runtime_api,
        instruction=instruction,
        current_text=current_text,
        required_h2=required_h2,
        required_outline=required_outline,
        expand_outline=expand_outline,
        analysis=analysis,
        analysis_summary=analysis_summary,
        paradigm_decision=paradigm_decision,
        forced_sections=forced_sections,
        settings=settings,
        agg_model=agg_model,
        capture_prompt_trace=_capture_prompt_trace,
        prompt_events=prompt_events,
    )
    if plan_state is None:
        return
    required_h2 = list(plan_state.get("required_h2") or [])
    required_outline = list(plan_state.get("required_outline") or [])
    title = str(plan_state.get("title") or "")
    sections = list(plan_state.get("sections") or [])
    paradigm_name = str(plan_state.get("paradigm_name") or "")
    force_required_outline_only = bool(plan_state.get("force_required_outline_only"))

    contract_state = yield from plan_domain.resolve_plan_contract_state(
        runtime_api=runtime_api,
        instruction=instruction,
        analysis=analysis,
        analysis_summary=analysis_summary,
        sections=sections,
        title=title,
        paradigm_name=paradigm_name,
        force_required_outline_only=force_required_outline_only,
        config=config,
        settings=settings,
        agg_model=agg_model,
        prompt_trace=prompt_trace,
        prompt_events=prompt_events,
        capture_prompt_trace=_capture_prompt_trace,
        build_final_event=_build_final_event,
    )
    if contract_state is None:
        return
    sections = list(contract_state.get("sections") or [])
    total_chars = int(contract_state.get("total_chars") or 0)
    section_contracts = dict(contract_state.get("section_contracts") or {})
    section_specs = list(contract_state.get("section_specs") or [])
    section_id_by_token = dict(contract_state.get("section_id_by_token") or {})
    plan_map = dict(contract_state.get("plan_map") or {})
    targets = dict(contract_state.get("targets") or {})

    support_keywords = evidence_domain._load_support_section_keywords()
    parent_map = runtime_api._map_section_parents(sections)
    section_models = {
        sec: (
            support_model
            if (support_model and evidence_domain._is_support_section(sec, support_keywords))
            else main_model
        )
        for sec in sections
    }
    runtime_api._record_phase_timing(run_id, {"phase": "PLAN", "event": "end"})
    yield {"event": "state", "name": "PLAN", "phase": "end"}
    runtime_api._record_phase_timing(run_id, {"phase": "DRAFT_SECTIONS", "event": "start", "sections": len(sections)})
    yield {"event": "state", "name": "DRAFT_SECTIONS", "phase": "start"}
    draft_start_ts = time.time()
    section_text: dict[str, str] = {str(spec.id): "" for spec in section_specs}
    evidence_map: dict[str, dict] = {}
    evidence_fact_rows: list[dict] = []
    data_starvation_rows: list[dict] = []
    rag_gate_dropped: list[dict] = []
    reference_sources: list[dict] = []
    reference_format_violations: list[dict] = []
    contract_slot_violations: list[dict] = []
    interrupted_sections: list[dict] = []
    originality = OriginalityTracker()
    completed = 0
    requested_min_total_chars = int(config.min_total_chars or 0)
    effective_min_total_chars = requested_min_total_chars
    reference_query = runtime_api._derive_reference_query(analysis=analysis, analysis_summary=analysis_summary, instruction=instruction)
    configured_min_ref_items = max(4, int(os.environ.get("WRITING_AGENT_MIN_REFERENCE_ITEMS", "18") or 18))
    rag_gate_enabled = _env_flag("WRITING_AGENT_RAG_THEME_GATE_ENABLED", "1")
    gate_title = graph_reference_domain.normalize_reference_query(str(analysis.get("topic") or "")) or reference_query or (analysis_summary or instruction).strip()
    min_theme_score = max(0.0, float(os.environ.get("WRITING_AGENT_RAG_THEME_MIN_SCORE", "0.25") or 0.25))
    fast_draft = _env_flag("WRITING_AGENT_FAST_DRAFT", "0")
    ensure_min = _env_flag("WRITING_AGENT_ENSURE_MIN_LENGTH", "1") and (not strict_json)
    enforce_meta = _env_flag("WRITING_AGENT_ENFORCE_META_FIREWALL", "1")

    def _sec_id(token: str) -> str:
        return str(section_id_by_token.get(token) or token)

    def _get_section_text(token: str) -> str:
        return str(section_text.get(_sec_id(token)) or "")

    def _set_section_text(token: str, value: str) -> None:
        section_text[_sec_id(token)] = str(value or "")

    for sec in sections:
        sec_title = runtime_api._section_title(sec) or sec
        sec_id = _sec_id(sec)
        sec_t = targets.get(sec) or runtime_api.SectionTargets(weight=1.0, min_paras=config.min_section_paragraphs, min_chars=0, max_chars=0, min_tables=0, min_figures=0)
        plan = plan_map.get(sec)
        model = section_models.get(sec) or main_model or settings.model
        if installed and model not in installed:
            model = settings.model
        yield {"event": "section", "phase": "start", "section": sec, "section_id": sec_id, "title": sec_title, "ts": time.time()}
        local_q: queue.Queue[dict] = queue.Queue()
        evidence_pack = runtime_api._default_evidence_pack()
        if runtime_api._is_evidence_enabled() and (not runtime_api._is_reference_section(sec_title)):
            evidence_pack, _cache_hit = runtime_api._load_evidence_pack_cached(local_cache=local_cache, cache_lock=cache_io_lock, provider_name=provider_name, model=model, instruction=instruction, section=sec, analysis=analysis, plan=plan, base_url=settings.base_url)
        evidence_map[sec] = evidence_pack
        starve = evidence_pack.get("data_starvation") if isinstance(evidence_pack, dict) else None
        evidence_fact_rows.append({"section": sec, "title": sec_title, "fact_gain_count": int((evidence_pack or {}).get("fact_gain_count") or 0), "fact_density_score": float((evidence_pack or {}).get("fact_density_score") or 0.0), "online_hits": int((evidence_pack or {}).get("online_hits") or 0), "stub_mode": bool((starve or {}).get("stub_mode")) if isinstance(starve, dict) else False})
        if isinstance(starve, dict) and bool(starve.get("is_starved")):
            data_starvation_rows.append({"section": sec, "title": sec_title, "reasons": [str(x).strip() for x in (starve.get("reasons") or []) if str(x).strip()], "alignment_score": float(starve.get("alignment_score") or 0.0), "compact_chars": int(starve.get("compact_chars") or 0), "source_count": int(starve.get("source_count") or 0), "status": str(starve.get("status") or "warning")})
            yield {"event": "rag_data_starvation", "count": len(data_starvation_rows), "rows": data_starvation_rows[:20]}
        yield {"event": "evidence_fact_metrics", "rows": evidence_fact_rows[:20]}

        if runtime_api._is_reference_section(sec_title):
            completed += 1
            yield {"event": "section", "phase": "end", "section": sec, "section_id": sec_id, "title": sec_title, "chars": 0, "ts": time.time()}
            continue

        source_rows = collect_source_rows(evidence_pack=evidence_pack, reference_sources=reference_sources)
        stream_kwargs = {"base_url": settings.base_url, "model": model, "title": title, "section": (f"{parent_map.get(sec)} / {sec_title}" if parent_map.get(sec) else sec_title), "section_id_override": sec_id, "parent_section": parent_map.get(sec) or "", "instruction": instruction, "analysis_summary": writer_requirement or instruction, "evidence_summary": str((evidence_pack or {}).get("summary") or "").strip(), "allowed_urls": list((evidence_pack or {}).get("allowed_urls") or []), "plan_hint": evidence_domain._format_plan_hint(plan), "min_paras": max(1, int(sec_t.min_paras or 1)), "min_chars": max(0, int(sec_t.min_chars or 0)), "max_chars": max(0, int(sec_t.max_chars or 0)), "min_tables": max(0, int(sec_t.min_tables or 0)), "min_figures": max(0, int(sec_t.min_figures or 0)), "out_queue": local_q, "reference_items": reference_sources, "text_store": text_store}
        draft = ""
        fast_draft_rejected = False
        if fast_draft:
            try:
                draft = runtime_api._fast_fill_section(sec, min_paras=max(1, int(sec_t.min_paras or 1)), min_chars=max(0, int(sec_t.min_chars or 0)), min_tables=max(0, int(sec_t.min_tables or 0)), min_figures=max(0, int(sec_t.min_figures or 0)))
            except Exception:
                draft = ""
            if draft:
                hot = evaluate_hot_sample(text=draft, source_rows=source_rows)
                originality.emit_metrics(out_queue=local_q, section=sec, section_id=sec_id, title=sec_title, metrics=hot, phase="fast_draft")
                if bool(hot.get("checked")) and (not bool(hot.get("passed", True))):
                    originality.record_action(section=sec, section_id=sec_id, title=sec_title, action="fast_draft_rejected")
                    local_q.put({"event": "section_fast_draft_rejected", "section": sec, "section_id": sec_id, "title": sec_title, "feedback": build_feedback(hot)})
                    fast_draft_rejected = True
                    draft = ""

        should_defer_to_strict_json_recovery = bool(strict_json and fast_draft and not draft and not fast_draft_rejected)
        if not draft and (not should_defer_to_strict_json_recovery):
            draft, _used_segment_split = runtime_api._draft_section_with_optional_segments(section_key=sec, section_title=sec_title, section_id=sec_id, plan=plan, contract=section_contracts.get(sec), targets=sec_t, out_queue=local_q, text_store=text_store, stream_kwargs=stream_kwargs)
            hot = evaluate_hot_sample(text=draft, source_rows=source_rows)
            originality.emit_metrics(out_queue=local_q, section=sec, section_id=sec_id, title=sec_title, metrics=hot, phase="initial")
            if bool(hot.get("checked")) and (not bool(hot.get("passed", True))):
                rewritten, changed = rewrite_for_originality(runtime_api, section_key=sec, section_id=sec_id, section_title=sec_title, model=model, draft_text=draft, metrics=hot, source_rows=source_rows, out_queue=local_q)
                if changed:
                    originality.record_action(section=sec, section_id=sec_id, title=sec_title, action="rewrite")
                    local_q.put({"event": "section_originality_hot_sample_rewrite", "section": sec, "section_id": sec_id, "title": sec_title})
                    draft = rewritten
                    hot2 = evaluate_hot_sample(text=draft, source_rows=source_rows)
                    originality.emit_metrics(out_queue=local_q, section=sec, section_id=sec_id, title=sec_title, metrics=hot2, phase="post_rewrite")

        if enforce_meta and draft:
            hits = runtime_api._meta_firewall_scan(draft)
            if hits:
                stripped = runtime_api._meta_firewall_strip(draft)
                draft = stripped if stripped.strip() else draft
        if ensure_min and draft:
            draft = runtime_api._ensure_section_minimums_stream(base_url=settings.base_url, model=model, title=title, section=(f"{parent_map.get(sec)} / {sec_title}" if parent_map.get(sec) else sec_title), parent_section=parent_map.get(sec) or "", instruction=instruction, analysis_summary=writer_requirement or instruction, evidence_summary=str((evidence_pack or {}).get("summary") or "").strip(), allowed_urls=list((evidence_pack or {}).get("allowed_urls") or []), plan_hint=evidence_domain._format_plan_hint(plan), dimension_hints=list((section_contracts.get(sec).dimension_hints if section_contracts.get(sec) else []) or []), draft=draft, min_paras=max(1, int(sec_t.min_paras or 1)), min_chars=max(0, int(sec_t.min_chars or 0)), max_chars=max(0, int(sec_t.max_chars or 0)), min_tables=max(0, int(sec_t.min_tables or 0)), min_figures=max(0, int(sec_t.min_figures or 0)), out_queue=local_q)
        _set_section_text(sec, draft)
        for ev in _drain_queue(local_q):
            yield ev
        completed += 1
        yield {"event": "section", "phase": "end", "section": sec, "section_id": sec_id, "title": sec_title, "chars": evidence_domain._section_body_len(draft), "ts": time.time()}

    if requested_min_total_chars > 0 and sections:
        non_ref_sections = [sec for sec in sections if not runtime_api._is_reference_section(runtime_api._section_title(sec) or sec)]
        fact_gain_total = sum(int(row.get("fact_gain_count") or 0) for row in evidence_fact_rows)
        density_values = [float(row.get("fact_density_score") or 0.0) for row in evidence_fact_rows]
        avg_density = (sum(density_values) / len(density_values)) if density_values else 0.0
        chars_per_fact = max(80.0, min(140.0, 90.0 + avg_density * 120.0))
        floor_chars = max(0, len(non_ref_sections) * 220)
        estimated_supported_chars = max(floor_chars, int(round(fact_gain_total * chars_per_fact)))
        if data_starvation_rows:
            estimated_supported_chars = max(floor_chars, int(round(estimated_supported_chars * 0.9)))
        if 0 < estimated_supported_chars < requested_min_total_chars:
            effective_min_total_chars = estimated_supported_chars
            yield {"event": "fact_density_target_adjustment", "requested_min_total_chars": requested_min_total_chars, "effective_min_total_chars": effective_min_total_chars, "fact_gain_total": fact_gain_total, "avg_fact_density_score": round(avg_density, 4)}

    reference_sources = evidence_domain._collect_reference_sources(evidence_map, query=reference_query)
    if (not reference_sources) and reference_query:
        reference_sources = runtime_api._fallback_reference_sources(instruction=reference_query)
    if rag_gate_enabled and reference_sources:
        gate = runtime_api._rag_theme_entity_gate(title=gate_title, sources=reference_sources, min_theme_score=min_theme_score, mode="reference")
        rag_gate_dropped = [row for row in (gate.get("dropped") or []) if isinstance(row, dict)]
        reference_sources = [row for row in (gate.get("kept") or []) if isinstance(row, dict)]
        if rag_gate_dropped:
            yield {"event": "rag_gate", "kept_count": len(reference_sources), "dropped_count": len(rag_gate_dropped), "dropped": rag_gate_dropped[:20]}
    before_count = len(_format_reference_items(reference_sources))
    if reference_query and before_count < configured_min_ref_items:
        repair_sources = runtime_api._fallback_reference_sources(instruction=reference_query)
        merged_sources = []
        seen_keys: set[str] = set()
        for row in list(reference_sources) + list(repair_sources or []):
            if not isinstance(row, dict):
                continue
            key = str(row.get("url") or row.get("id") or row.get("title") or "").strip().lower()
            if (not key) or key in seen_keys:
                continue
            seen_keys.add(key)
            merged_sources.append(dict(row))
        dropped2: list[dict] = []
        if rag_gate_enabled and merged_sources:
            gate2 = runtime_api._rag_theme_entity_gate(title=gate_title, sources=merged_sources, min_theme_score=min_theme_score, mode="reference")
            dropped2 = [row for row in (gate2.get("dropped") or []) if isinstance(row, dict)]
            merged_sources = [row for row in (gate2.get("kept") or []) if isinstance(row, dict)]
            rag_gate_dropped.extend(dropped2)
        after_count = len(_format_reference_items(merged_sources))
        if after_count >= before_count:
            reference_sources = merged_sources
        yield {"event": "reference_repair", "query": reference_query, "before_count": before_count, "after_count": after_count, "added_sources": max(0, len(reference_sources) - before_count), "dropped_count": len(dropped2)}
    reference_sources = runtime_api._sort_reference_sources(reference_sources, query=reference_query)
    for sec in sections:
        sec_title = runtime_api._section_title(sec) or sec
        if not runtime_api._is_reference_section(sec_title):
            continue
        refs = _format_reference_items(reference_sources)
        issues = runtime_api._validate_reference_items(refs)
        if issues:
            reference_format_violations.append({"section": sec, "title": sec_title, "issues": list(issues)})
        _set_section_text(sec, "\n".join(refs).strip())

    runtime_api._record_phase_timing(run_id, {"phase": "DRAFT_SECTIONS", "event": "end", "duration_s": time.time() - draft_start_ts})
    yield {"event": "state", "name": "DRAFT_SECTIONS", "phase": "end"}
    runtime_api._record_phase_timing(run_id, {"phase": "AGGREGATE", "event": "start"})
    yield {"event": "state", "name": "AGGREGATE", "phase": "start"}

    if strict_json:
        missing = [sec for sec in sections if (not (_get_section_text(sec) or "").strip()) and (not runtime_api._is_reference_section(runtime_api._section_title(sec) or sec))]
        if missing:
            yield {"event": "strict_json_recovery", "attempt": 1, "missing_sections": [(runtime_api._section_title(s) or s) for s in missing], "strategy": "targeted_regeneration"}
            for sec in missing:
                sec_title = runtime_api._section_title(sec) or sec
                sec_id = _sec_id(sec)
                sec_t = targets.get(sec) or runtime_api.SectionTargets(weight=1.0, min_paras=config.min_section_paragraphs, min_chars=800, max_chars=0, min_tables=0, min_figures=0)
                plan = plan_map.get(sec)
                repair_q: queue.Queue[dict] = queue.Queue()
                try:
                    repaired = runtime_api._generate_section_stream(base_url=settings.base_url, model=section_models.get(sec) or main_model, title=title, section=(f"{parent_map.get(sec)} / {sec_title}" if parent_map.get(sec) else sec_title), section_id_override=sec_id, parent_section=parent_map.get(sec) or "", instruction=instruction, analysis_summary=writer_requirement or instruction, evidence_summary=str((evidence_map.get(sec) or {}).get("summary") or "").strip(), allowed_urls=list((evidence_map.get(sec) or {}).get("allowed_urls") or []), plan_hint=evidence_domain._format_plan_hint(plan), min_paras=max(2, int(sec_t.min_paras or config.min_section_paragraphs)), min_chars=max(200, int(sec_t.min_chars or 200)), max_chars=max(0, int(sec_t.max_chars or 0)), min_tables=max(0, int(sec_t.min_tables or 0)), min_figures=max(0, int(sec_t.min_figures or 0)), out_queue=repair_q, reference_items=reference_sources, text_store=text_store)
                    if repaired and str(repaired).strip():
                        _set_section_text(sec, str(repaired).strip())
                except Exception:
                    pass
                for ev in _drain_queue(repair_q):
                    yield ev
            missing = [sec for sec in sections if (not (_get_section_text(sec) or "").strip()) and (not runtime_api._is_reference_section(runtime_api._section_title(sec) or sec))]
        if missing:
            reason = "strict_json_missing_sections"
            missing_titles = [(runtime_api._section_title(s) or s) for s in missing]
            yield {"event": "strict_json_recovery", "attempt": 2, "missing_sections": missing_titles, "strategy": "stub_mode"}
            yield _build_final_event(text="", problems=[reason] + missing_titles, status="failed", failure_reason=f"{reason}:{','.join(missing_titles)}", quality_snapshot={"status": "failed", "reason": reason, "missing_sections": missing_titles, "strict_json_recovery_attempts": 2}, runtime_status="failed", runtime_failure_reason=f"{reason}:{','.join(missing_titles)}", quality_passed=False, quality_failure_reason=reason)
            return

    for sec in sections:
        sec_title = runtime_api._section_title(sec) or sec
        contract = section_contracts.get(sec)
        if not contract:
            continue
        original = str(_get_section_text(sec) or "")
        updated = runtime_api._apply_contract_slot_filling(section_title=sec_title, text=original, analysis=analysis, contract=contract)
        if updated != original:
            _set_section_text(sec, updated)
            yield {"event": "section_contract_applied", "section": sec, "title": sec_title, "mode": "slot_filling"}
        slot_issues = runtime_api._validate_contract_slots(section_title=sec_title, text=str(_get_section_text(sec) or ""), contract=contract)
        if slot_issues:
            contract_slot_violations.append({"section": sec, "title": sec_title, "issues": list(slot_issues)})

    merged, assembly_map = assemble_by_id_map(title=title, section_specs=section_specs, content_by_id=section_text)
    merged = runtime_api._sanitize_output_text(merged)
    if ensure_min:
        for sec in sections:
            sec_title = runtime_api._section_title(sec) or sec
            if runtime_api._is_reference_section(sec_title):
                continue
            sec_t = targets.get(sec)
            if not sec_t:
                continue
            evidence_pack = evidence_map.get(sec) or runtime_api._default_evidence_pack()
            plan = plan_map.get(sec)
            contract = section_contracts.get(sec)
            _set_section_text(sec, runtime_api._ensure_section_minimums_stream(base_url=settings.base_url, model=section_models.get(sec) or main_model or settings.model, title=title, section=(f"{parent_map.get(sec)} / {sec_title}" if parent_map.get(sec) else sec_title), parent_section=parent_map.get(sec) or "", instruction=instruction, analysis_summary=writer_requirement or instruction, evidence_summary=str((evidence_pack or {}).get("summary") or "").strip(), allowed_urls=list((evidence_pack or {}).get("allowed_urls") or []), plan_hint=evidence_domain._format_plan_hint(plan), dimension_hints=list((contract.dimension_hints if contract else []) or []), draft=_get_section_text(sec), min_paras=sec_t.min_paras, min_chars=sec_t.min_chars, max_chars=sec_t.max_chars, min_tables=sec_t.min_tables, min_figures=sec_t.min_figures, out_queue=queue.Queue()))
        merged, assembly_map = assemble_by_id_map(title=title, section_specs=section_specs, content_by_id=section_text)
        merged = runtime_api._sanitize_output_text(merged)
    merged = runtime_api._normalize_final_output(merged, expected_sections=sections, title_override=title)
    section_missing_rows = [row.to_dict() for row in find_missing_sections(section_specs=section_specs, content_by_id=section_text, stage="aggregate")]
    problems = runtime_api._light_self_check(text=merged, sections=sections, target_chars=effective_min_total_chars or total_chars, evidence_enabled=runtime_api._is_evidence_enabled(), reference_sources=reference_sources)
    meta_residue_hits = runtime_api._meta_firewall_scan(merged) if enforce_meta else []
    if meta_residue_hits:
        problems.append("meta_residue_detected")
    data_starvation_gate = runtime_api._starvation_failure_decision(sections=sections, data_starvation_rows=data_starvation_rows, evidence_enabled=runtime_api._is_evidence_enabled())
    if bool(data_starvation_gate.get("triggered")):
        problems.append(str(data_starvation_gate.get("failure_reason") or "insufficient_fact_density"))
    final_validation = runtime_api._validate_final_document(title=title, text=merged, sections=sections, problems=problems, rag_gate_dropped=rag_gate_dropped, source_rows=reference_sources)
    reference_item_count = len(_format_reference_items(reference_sources))
    quality_passed, quality_failure_reason, terminal_status = finalize_domain.resolve_terminal_quality(
        problems=problems,
        reference_item_count=reference_item_count,
        configured_min_ref_items=configured_min_ref_items,
        enforce_meta=enforce_meta,
        meta_residue_hits=meta_residue_hits,
        enforce_reference_min=_env_flag("WRITING_AGENT_ENFORCE_REFERENCE_MIN", "1"),
        enforce_final_validation=_env_flag("WRITING_AGENT_ENFORCE_FINAL_VALIDATION", "1"),
        final_validation=final_validation,
    )
    quality_snapshot = finalize_domain.build_quality_snapshot(
        merged=merged,
        problems=problems,
        requested_min_total_chars=requested_min_total_chars,
        effective_min_total_chars=effective_min_total_chars,
        reference_item_count=reference_item_count,
        contract_slot_violations=contract_slot_violations,
        reference_format_violations=reference_format_violations,
        meta_residue_hits=meta_residue_hits,
        rag_gate_dropped=rag_gate_dropped,
        data_starvation_rows=data_starvation_rows,
        data_starvation_gate=data_starvation_gate,
        evidence_fact_rows=evidence_fact_rows,
        section_missing_rows=section_missing_rows,
        section_specs=section_specs,
        assembly_map=assembly_map,
        interrupted_sections=interrupted_sections,
        final_validation=final_validation,
        originality_summary=originality.summary(),
        body_len_fn=evidence_domain._doc_body_len,
    )
    runtime_api._record_phase_timing(run_id, {"phase": "AGGREGATE", "event": "end", "duration_s": time.time() - draft_start_ts})
    runtime_api._record_phase_timing(run_id, {"phase": "TOTAL", "event": "end", "duration_s": time.time() - run_start_ts})
    yield _build_final_event(text=merged, problems=problems, status=terminal_status, failure_reason=quality_failure_reason or "", quality_snapshot=quality_snapshot, runtime_status="success", runtime_failure_reason="", quality_passed=quality_passed, quality_failure_reason=quality_failure_reason)


__all__ = [name for name in globals() if not name.startswith("__")]
