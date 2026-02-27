"""Graph Runner Runtime module.

This module belongs to `writing_agent.v2` in the writing-agent codebase.
"""

from __future__ import annotations

from writing_agent.v2.graph_runner import *  # noqa: F401,F403

def run_generate_graph(
    *,
    instruction: str,
    current_text: str,
    required_h2: list[str] | None,
    required_outline: list[tuple[int, str]] | None = None,
    expand_outline: bool = False,
    config: GenerateConfig,
):
    """\n    Yields dict events suitable for SSE:\n      - {"event":"state","name":...,"phase":"start"|"end"}\n      - {"event":"plan","title":...,"sections":[...]}\n      - {"event":"section","phase":"start"|"delta"|"end","section":...,"delta":...}\n      - {"event":"final","text":...,"problems":[...]}\n    """
    settings = get_ollama_settings()
    strict_json_raw = os.environ.get("WRITING_AGENT_STRICT_JSON", "0").strip().lower()
    strict_json = strict_json_raw in {"1", "true", "yes", "on"}
    run_id = f"run_{int(time.time()*1000)}"
    run_start_ts = time.time()
    if not settings.enabled:
        raise OllamaError("Ollama is not enabled (WRITING_AGENT_USE_OLLAMA=0)")
    client = OllamaClient(base_url=settings.base_url, model=settings.model, timeout_s=settings.timeout_s)
    if not client.is_running():
        raise OllamaError("Ollama is not running")

    installed = _ollama_installed_models()
    def _normalize_model_name(name: str) -> str:
        n = (name or "").strip()
        if not n or n.lower() in {"name", "model", "default", "unknown"}:
            return settings.model
        if installed and n not in installed:
            return settings.model
        return n

    agg_model = config.aggregator_model or os.environ.get("WRITING_AGENT_AGG_MODEL", "").strip() or settings.model
    agg_model = _normalize_model_name(agg_model)
    if installed and agg_model not in installed:
        agg_model = settings.model

    worker_models = (config.worker_models or [])[:]
    if not worker_models:
        models_raw = os.environ.get("WRITING_AGENT_WORKER_MODELS", "").strip()
        if models_raw:
            worker_models = [m.strip() for m in models_raw.split(",") if m.strip()]
        else:
            worker_models = _default_worker_models(preferred=settings.model)

    # Prefer using smaller models for drafting; avoid using the aggregator model for drafts if possible.
    worker_models = _select_models_by_memory(worker_models, fallback=settings.model)
    if installed:
        worker_models = [m for m in worker_models if m in installed] or [settings.model]
    worker_models = [_normalize_model_name(m) for m in worker_models if m.strip()]
    if len(worker_models) > 1:
        worker_models = [m for m in worker_models if m != agg_model] or worker_models

    # Prefer more draft models by default to better use multi-core CPUs.
    draft_max = int(os.environ.get("WRITING_AGENT_DRAFT_MAX_MODELS", "3"))
    draft_max = max(2, min(4, draft_max))  # at least 2 models
    worker_models = worker_models[:draft_max] or [settings.model]

    pool = ModelPool(worker_models or [settings.model])

    # Initialize local caches.
    repo_root = Path(__file__).resolve().parents[2]
    data_dir = Path(os.environ.get("WRITING_AGENT_DATA_DIR", str(repo_root / ".data"))).resolve()
    cache_dir = data_dir / "cache"
    local_cache = LocalCache(cache_dir)
    phrase_cache = AcademicPhraseCache(cache_dir)
    text_store = TextStore(data_dir / "text_store")

    _record_phase_timing(run_id, {"phase": "PLAN", "event": "start"})
    yield {"event": "state", "name": "PLAN", "phase": "start"}
    analysis_start_ts = time.time()
    analysis = _analyze_instruction(
        base_url=settings.base_url,
        model=agg_model,
        instruction=instruction,
        current_text=current_text,
    )
    _record_phase_timing(run_id, {"phase": "ANALYSIS", "event": "end", "duration_s": time.time() - analysis_start_ts})
    analysis_summary = _format_analysis_summary(analysis, fallback=instruction)
    if analysis_summary:
        yield {"event": "delta", "delta": "Analysis completed with structured key points."}
    wants_ack = _wants_acknowledgement(instruction)
    if required_outline:
        required_outline = _filter_ack_outline(required_outline, allow_ack=wants_ack)
        required_outline = _filter_disallowed_outline(required_outline)
        required_outline = _sanitize_outline(required_outline)
    if required_h2:
        required_h2 = _filter_ack_headings(required_h2, allow_ack=wants_ack)
        required_h2 = _filter_disallowed_sections(required_h2)

    title = _plan_title(current_text=current_text, instruction=instruction)
    sections: list[str] = []
    if required_outline:
        sections, required_h2_effective = _sections_from_outline(required_outline, expand=expand_outline)
        if required_h2_effective:
            required_h2 = [
                _clean_outline_title(x) for x in required_h2_effective if _clean_outline_title(x)
            ]
        sections = _sanitize_section_tokens(sections, keep_full_titles=True)
    if not sections and required_h2:
        _, sections = _plan_title_sections(current_text=current_text, instruction=instruction, required_h2=required_h2)
    fast_plan_raw = os.environ.get("WRITING_AGENT_FAST_PLAN", "").strip().lower()
    fast_plan = fast_plan_raw in {"1", "true", "yes", "on"}
    if not sections:
        if fast_plan:
            sections = _default_outline_from_instruction(instruction) or [
                "Introduction",
                "This Week Work",
                "Issues and Risks",
                "Next Week Plan",
                "Support Needed",
            ]
        else:
            plan_list_start = time.time()
            sections = _plan_sections_list_with_model(
                base_url=settings.base_url,
                model=agg_model,
                title=title,
                instruction=analysis_summary or instruction,
            )
            _record_phase_timing(run_id, {"phase": "PLAN_SECTIONS", "event": "end", "duration_s": time.time() - plan_list_start})
    sections = [s for s in (sections or []) if (_section_title(s) or "").strip()]
    if not sections:
        sections = [
            "Introduction",
            "Requirement Analysis",
            "Overall Design",
            "Data Design",
            "Testing and Results",
            "Conclusion",
            "References",
        ]
    total_chars = _target_total_chars(config)
    base_targets = _compute_section_targets(sections=sections, base_min_paras=config.min_section_paragraphs, total_chars=total_chars)
    if fast_plan:
        plan_map = _default_plan_map(sections=sections, base_targets=base_targets, total_chars=total_chars)
    else:
        plan_detail_start = time.time()
        plan_raw = _plan_sections_with_model(
            base_url=settings.base_url,
            model=agg_model,
            title=title,
            instruction=analysis_summary or instruction,
            sections=sections,
            total_chars=total_chars,
        )
        _record_phase_timing(run_id, {"phase": "PLAN_DETAIL", "event": "end", "duration_s": time.time() - plan_detail_start})
        plan_map = _normalize_plan_map(
            plan_raw=plan_raw,
            sections=sections,
            base_targets=base_targets,
            total_chars=total_chars,
        )
    try:
        struct_plan = {"title": title, "total_chars": total_chars, "sections": []}
        for sec in sections:
            plan = plan_map.get(sec)
            if not plan:
                continue
            struct_plan["sections"].append({
                "title": _section_title(sec) or sec,
                "target_chars": int(plan.target_chars or 0),
                "key_points": list(plan.key_points or [])[:6],
                "figures": list(plan.figures or [])[:2],
                "tables": list(plan.tables or [])[:2],
                "evidence_queries": list(plan.evidence_queries or [])[:4],
            })
        yield {"event": "struct_plan", "plan": struct_plan}
    except Exception:
        pass
    targets: dict[str, SectionTargets] = {}
    for sec in sections:
        base = base_targets.get(sec)
        plan = plan_map.get(sec)
        if not plan:
            continue
        targets[sec] = SectionTargets(
            weight=base.weight if base else 1.0,
            min_paras=base.min_paras if base else config.min_section_paragraphs,
            min_chars=plan.min_chars,
            max_chars=plan.max_chars,
            min_tables=plan.min_tables,
            min_figures=plan.min_figures,
        )
    if _is_engineering_instruction(instruction):
        _boost_media_targets(targets, sections)
        plan_map = _sync_plan_media(plan_map, targets)
    main_model, support_model = _pick_draft_models(worker_models, agg_model=agg_model, fallback=settings.model)
    main_model = main_model or settings.model
    main_model = _normalize_model_name(main_model)
    support_model = _normalize_model_name(support_model or "") if support_model else ""
    support_keywords = _load_support_section_keywords()
    parent_map = _map_section_parents(sections)
    section_models = {
        sec: (support_model if (support_model and _is_support_section(sec, support_keywords)) else main_model)
        for sec in sections
    }
    yield {"event": "plan", "title": title, "sections": sections}
    yield {"event": "targets", "targets": {k: targets[k].__dict__ for k in sections if k in targets}}
    yield {"event": "delta", "delta": f"Draft models: main={main_model}, support={support_model or '[none]'}; planner/validator={agg_model}"}
    _record_phase_timing(run_id, {"phase": "PLAN", "event": "end"})
    yield {"event": "state", "name": "PLAN", "phase": "end"}

    _record_phase_timing(run_id, {"phase": "DRAFT_SECTIONS", "event": "start", "sections": len(sections)})
    yield {"event": "state", "name": "DRAFT_SECTIONS", "phase": "start"}
    draft_start_ts = time.time()
    q: queue.Queue[dict] = queue.Queue()
    section_text: dict[str, str] = {s: "" for s in sections}
    evidence_map: dict[str, dict] = {}
    evidence_enabled = _is_evidence_enabled()
    if sections and evidence_enabled:
        evidence_start_ts = time.time()
        _record_phase_timing(run_id, {"phase": "EVIDENCE_PREP", "event": "start", "sections": len(sections)})
        yield {"event": "delta", "delta": "Preparing sources for drafting..."}
        evidence_timeout_s = float(os.environ.get("WRITING_AGENT_EVIDENCE_TIMEOUT_S", "40"))
        evidence_workers = max(1, int(os.environ.get("WRITING_AGENT_EVIDENCE_WORKERS", "3")))
        evidence_workers = min(evidence_workers, max(1, len(sections)))
        evidence_starts: dict[str, float] = {}
        fut_map: dict[object, str] = {}
        ev_pool = ThreadPoolExecutor(max_workers=evidence_workers)
        try:
            for sec in sections:
                plan = plan_map.get(sec)
                evidence_starts[sec] = time.time()
                fut = ev_pool.submit(
                    _build_evidence_pack,
                    instruction=analysis_summary or instruction,
                    section=sec,
                    analysis=analysis,
                    plan=plan,
                    base_url=settings.base_url,
                    model=agg_model,
                )
                fut_map[fut] = sec
            done, not_done = wait(set(fut_map.keys()), timeout=evidence_timeout_s)
            for fut in done:
                sec = fut_map.get(fut, "")
                try:
                    evidence_map[sec] = fut.result()
                except Exception:
                    evidence_map[sec] = {"summary": "", "sources": [], "allowed_urls": []}
            for fut in not_done:
                sec = fut_map.get(fut, "")
                fut.cancel()
                evidence_map[sec] = {"summary": "", "sources": [], "allowed_urls": []}
            for sec in sections:
                sec_start = evidence_starts.get(sec, time.time())
                _record_phase_timing(
                    run_id,
                    {
                        "phase": "EVIDENCE_SECTION",
                        "event": "end",
                        "section": _section_title(sec) or sec,
                        "duration_s": time.time() - sec_start,
                    },
                )
        finally:
            ev_pool.shutdown(wait=False, cancel_futures=True)
        _record_phase_timing(
            run_id,
            {
                "phase": "EVIDENCE_PREP",
                "event": "end",
                "duration_s": time.time() - evidence_start_ts,
            },
        )
    else:
        for sec in sections:
            evidence_map[sec] = {"summary": "", "sources": [], "allowed_urls": []}
    reference_sources: list[dict] = []
    ref_start = time.time()
    reference_sources = _collect_reference_sources(evidence_map)
    _record_phase_timing(run_id, {"phase": "REF_SOURCES", "event": "end", "duration_s": time.time() - ref_start})
    if not reference_sources:
        ref_fb_start = time.time()
        reference_sources = _fallback_reference_sources(instruction=analysis_summary or instruction)
        _record_phase_timing(run_id, {"phase": "REF_FALLBACK", "event": "end", "duration_s": time.time() - ref_fb_start})

    def worker(section: str, model: str) -> None:
        sec_start_ts = time.time()
        attempts = max(1, int(os.environ.get("WRITING_AGENT_SECTION_RETRIES", "2")))
        last_err: Exception | None = None
        sec_t = targets.get(section) or SectionTargets(weight=1.0, min_paras=config.min_section_paragraphs, min_chars=800, max_chars=0, min_tables=0, min_figures=0)
        plan = plan_map.get(section)
        plan_hint = _format_plan_hint(plan)
        evidence = evidence_map.get(section) or {}
        evidence_summary = str(evidence.get("summary") or "").strip()
        allowed_urls = evidence.get("allowed_urls") or []
        sec_title = _section_title(section) or section
        parent_title = parent_map.get(section) or ""
        if parent_title:
            sec_label = f"{parent_title} / {sec_title}"
        else:
            sec_label = sec_title
        # Try cache first to reduce repeated generation for identical requests.
        q.put({"event": "section", "phase": "start", "section": section, "title": sec_label, "ts": time.time()})
        
        # 妫€鏌ョ紦瀛?
        cached = local_cache.get_section(sec_title, instruction, sec_t.min_chars)
        if cached and len(cached.strip()) > 100:
            section_text[section] = cached
            q.put({"event": "section", "phase": "delta", "section": section, "delta": cached})
            q.put({"event": "section", "phase": "end", "section": section, "ts": time.time()})
            _record_phase_timing(
                run_id,
                {"phase": "SECTION_REAL", "event": "end", "section": sec_label, "duration_s": time.time() - sec_start_ts},
            )
            return
        
        fast_mode = os.environ.get("WRITING_AGENT_FAST_DRAFT", "").strip().lower() in {"1", "true", "yes", "on"}
        if fast_mode:
            txt_fast = _fast_fill_section(
                section,
                min_paras=sec_t.min_paras,
                min_chars=sec_t.min_chars,
                min_tables=sec_t.min_tables,
                min_figures=sec_t.min_figures,
            )
            section_text[section] = txt_fast
            q.put({"event": "section", "phase": "delta", "section": section, "delta": txt_fast})
            q.put({"event": "section", "phase": "end", "section": section, "ts": time.time()})
            _record_phase_timing(
                run_id,
                {"phase": "SECTION_REAL", "event": "end", "section": sec_label, "duration_s": time.time() - sec_start_ts},
            )
            return
        for attempt in range(1, attempts + 1):
            try:
                if attempt > 1:
                    q.put({"event": "section", "phase": "delta", "section": section, "delta": f"\n\n[Retry {attempt}/{attempts}] "})
                    time.sleep(0.8 * attempt)
                txt = _generate_section_stream(
                    base_url=settings.base_url,
                    model=model,
                    title=title,
                    section=sec_label,
                    parent_section=parent_title,
                    instruction=instruction,
                    plan_hint=plan_hint,
                    analysis_summary=analysis_summary or instruction,
                    evidence_summary=evidence_summary,
                    allowed_urls=allowed_urls,
                    reference_items=reference_sources,
                    min_paras=sec_t.min_paras,
                    min_chars=sec_t.min_chars,
                    max_chars=sec_t.max_chars,
                    min_tables=sec_t.min_tables,
                    min_figures=sec_t.min_figures,
                    out_queue=q,
                    text_store=text_store,
                )
                txt2 = _postprocess_section(
                    section,
                    txt,
                    min_paras=sec_t.min_paras,
                    min_chars=sec_t.min_chars,
                    max_chars=sec_t.max_chars,
                    min_tables=sec_t.min_tables,
                    min_figures=sec_t.min_figures,
                )
                section_text[section] = txt2
                # 存入缓存
                if txt2 and len(txt2.strip()) > 100:
                    local_cache.put_section(sec_title, instruction, sec_t.min_chars, txt2)
                q.put({"event": "section", "phase": "end", "section": section, "ts": time.time()})
                _record_phase_timing(
                    run_id,
                    {"phase": "SECTION_REAL", "event": "end", "section": sec_label, "duration_s": time.time() - sec_start_ts},
                )
                return
            except Exception as e:
                last_err = e
                q.put({"event": "section", "phase": "retry", "section": section, "attempt": attempt, "error": str(e)[:100]})
                continue
        if last_err is not None:
            q.put({"event": "section_error", "section": section, "reason": str(last_err)[:200]})
        strict_json_raw = os.environ.get("WRITING_AGENT_STRICT_JSON", "0").strip().lower()
        if strict_json_raw in {"1", "true", "yes", "on"}:
            return
        if _is_reference_section(_section_title(section) or section):
            fallback = _fast_fill_references(section)
        else:
            fallback = _generic_fill_paragraph(section, idx=1)
        section_text[section] = fallback
        q.put({"event": "section", "phase": "delta", "section": section, "delta": fallback})
        q.put({"event": "section", "phase": "end", "section": section, "ts": time.time()})
        _record_phase_timing(
            run_id,
            {"phase": "SECTION_REAL", "event": "end", "section": sec_label, "duration_s": time.time() - sec_start_ts},
        )

    unique_models = sorted({m for m in section_models.values() if m})
    per_model = max(1, int(os.environ.get("WRITING_AGENT_PER_MODEL_CONCURRENCY", "1")))
    cap = max(1, per_model * max(1, len(unique_models)))
    requested = max(1, int(config.workers))
    max_workers = max(1, min(12, min(requested, cap)))  # 8鈫?2 閫傞厤楂樻€ц兘CPU

    # Parallel drafting enabled by default; cap by model-count and CPU budget.
    parallel_raw = os.environ.get("WRITING_AGENT_DRAFT_PARALLEL", "1").strip().lower()  # default enabled: "1"
    parallel = parallel_raw in {"1", "true", "yes", "on"}
    # Only force serial mode when explicitly disabled by env var.
    if not parallel:
        max_workers = 1  # strict serial mode
    elif len(unique_models) <= 1:
        max_workers = min(max_workers, 8)  # allow higher parallelism for single-model runs

    # Manage thread pool manually to avoid generator/context-manager conflicts.
    ex = ThreadPoolExecutor(max_workers=max_workers)
    try:
        futs = []
        for sec in sections:
            futs.append(ex.submit(worker, sec, section_models.get(sec) or main_model))

        completed: set[str] = set()
        total_sections = len(sections)
        last_progress_time = time.time()
        section_start_ts: dict[str, float] = {}
        while True:
            try:
                ev = q.get(timeout=0.1)  # 0.2鈫?.1 鎻愬崌鍝嶅簲閫熷害
                if isinstance(ev, dict) and ev.get("event") == "section":
                    sec_name = str(ev.get("section") or "")
                    phase = str(ev.get("phase") or "")
                    if phase == "start" and sec_name:
                        ev_ts = float(ev.get("ts") or time.time())
                        section_start_ts[sec_name] = ev_ts
                    elif phase == "end" and sec_name:
                        start_ts = section_start_ts.pop(sec_name, None)
                        if start_ts:
                            end_ts = float(ev.get("ts") or time.time())
                            _record_phase_timing(
                                run_id,
                                {
                                    "phase": "SECTION",
                                    "event": "end",
                                    "section": sec_name,
                                    "duration_s": end_ts - start_ts,
                                },
                            )
                if (
                    isinstance(ev, dict)
                    and ev.get("event") == "section"
                    and ev.get("phase") == "end"
                    and total_sections
                ):
                    sec = str(ev.get("section") or "")
                    if sec and sec not in completed:
                        completed.add(sec)
                        yield ev
                        pct = int((len(completed) / max(1, total_sections)) * 100)
                        elapsed_s = int(time.time() - draft_start_ts) if draft_start_ts else 0
                        
                        # Throttle progress events to avoid flooding frontend render pipeline.
                        now = time.time()
                        if now - last_progress_time >= 0.5:  # 鏈€澶氭瘡0.5s鍙戦€佷竴娆?
                            yield {
                                "event": "progress",
                                "current": len(completed),
                                "total": total_sections,
                                "percent": pct,
                                "section": sec,
                                "elapsed_s": elapsed_s,
                            }
                            last_progress_time = now
                        yield {"event": "delta", "delta": f"Completed {len(completed)}/{total_sections}"}
                        continue
                yield ev
                continue
            except queue.Empty:
                pass
            done_count = sum(1 for f in futs if f.done())
            if done_count == len(futs) and q.empty():
                break
        
        # Ensure all workers are finalized via Future.result() before exit.
        for f in futs:
            try:
                f.result(timeout=1.0)  # 姣忎釜鏈€澶氱瓑1绉?
            except Exception:
                pass  # 蹇界暐寮傚父,缁х画澶勭悊涓嬩竴涓?
    finally:
        # Do not call shutdown() from inside generator; cancel unfinished futures instead.
        for f in futs:
            if not f.done():
                f.cancel()

    _record_phase_timing(run_id, {"phase": "DRAFT_SECTIONS", "event": "end", "duration_s": time.time() - draft_start_ts})
    yield {"event": "state", "name": "DRAFT_SECTIONS", "phase": "end"}

    agg_start_ts = time.time()
    agg_recorded = False
    _record_phase_timing(run_id, {"phase": "AGGREGATE", "event": "start"})
    yield {"event": "state", "name": "AGGREGATE", "phase": "start"}
    validate_raw = os.environ.get("WRITING_AGENT_VALIDATE_PLAN", "1").strip().lower()
    validate_plan = validate_raw in {"1", "true", "yes", "on"}
    ensure_min_raw = os.environ.get("WRITING_AGENT_ENSURE_MIN_LENGTH", "1").strip().lower()
    ensure_min = ensure_min_raw in {"1", "true", "yes", "on"}
    if strict_json:
        # Keep strict schema output, but avoid disabling length floor by default.
        validate_plan = False
    if validate_plan:
        yield {"event": "delta", "delta": "Planning validation?"}
    else:
        yield {"event": "delta", "delta": "Skip validation and continue to aggregate output."}
    if strict_json:
        missing = [sec for sec in sections if not (section_text.get(sec) or "").strip()]
        if missing:
            raise ValueError(f"strict_json: empty sections: {', '.join([_section_title(s) or s for s in missing])}")
    else:
        for sec in sections:
            if not (section_text.get(sec) or "").strip():
                if _is_reference_section(_section_title(sec) or sec):
                    section_text[sec] = "\n".join(_format_reference_items(reference_sources or [])).strip()
                else:
                    section_text[sec] = _generic_fill_paragraph(sec, idx=1)
    
    merged = _sanitize_output_text(_merge_sections_text(title, sections, section_text))

    issues: list[dict] = []
    if validate_plan:
        issues = _validate_plan_results(
            base_url=settings.base_url,
            model=agg_model,
            title=title,
            instruction=analysis_summary or instruction,
            sections=sections,
            plan_map=plan_map,
            section_text=section_text,
        )

    if (validate_plan and not issues) or (not validate_plan and ensure_min):
        for sec in sections:
            sec_title = _section_title(sec) or sec
            if _is_reference_section(sec_title):
                continue
            plan = plan_map.get(sec)
            if not plan:
                continue
            length = _section_body_len(section_text.get(sec) or "")
            if ensure_min and length < plan.min_chars:
                ctx = _maybe_rag_context(instruction=instruction, section=sec_title)
                expanded = _expand_with_context(
                    sec,
                    section_text.get(sec) or "",
                    ctx,
                    plan.min_chars,
                    targets.get(sec).min_paras if targets.get(sec) else config.min_section_paragraphs,
                    plan,
                )
                if expanded:
                    section_text[sec] = expanded
                    length = _section_body_len(expanded)
            if length < plan.min_chars:
                issues.append({"title": plan.title, "issue": "short", "action": "expand"})
            elif plan.max_chars > 0 and length > plan.max_chars:
                issues.append({"title": plan.title, "issue": "long", "action": "trim"})

    if issues:
        fix_queue = queue.Queue()
        title_map = {(_section_title(sec) or sec): sec for sec in sections}
        for item in issues:
            title_key = str(item.get("title") or "").strip()
            if not title_key:
                continue
            sec_key = title_map.get(title_key)
            if not sec_key:
                continue
            plan = plan_map.get(sec_key)
            if not plan:
                continue
            action = str(item.get("action") or "").lower()
            issue = str(item.get("issue") or "").lower()
            if action == "expand" or issue == "short":
                model = section_models.get(sec_key) or main_model
                if installed and model not in installed:
                    model = settings.model
                plan_hint = _format_plan_hint(plan)
                evidence = evidence_map.get(sec_key) or {}
                evidence_summary = str(evidence.get("summary") or "").strip()
                allowed_urls = evidence.get("allowed_urls") or []
                try:
                    fixed = _ensure_section_minimums_stream(
                        base_url=settings.base_url,
                        model=model,
                        title=title,
                        section=_section_title(sec_key) or sec_key,
                        parent_section=parent_map.get(sec_key) or "",
                        instruction=analysis_summary or instruction,
                        analysis_summary=analysis_summary or instruction,
                        evidence_summary=evidence_summary,
                        allowed_urls=allowed_urls,
                        plan_hint=plan_hint,
                        draft=section_text.get(sec_key) or "",
                        min_paras=targets.get(sec_key).min_paras if targets.get(sec_key) else config.min_section_paragraphs,
                        min_chars=plan.min_chars,
                        max_chars=plan.max_chars,
                        min_tables=plan.min_tables,
                        min_figures=plan.min_figures,
                        out_queue=fix_queue,
                    )
                    section_text[sec_key] = fixed
                except Exception:
                    section_text[sec_key] = section_text.get(sec_key) or ""
            elif action == "trim" or issue == "long":
                sec_min_paras = targets.get(sec_key).min_paras if targets.get(sec_key) else config.min_section_paragraphs
                trimmed = _postprocess_section(
                    sec_key,
                    section_text.get(sec_key) or "",
                    min_paras=sec_min_paras,
                    min_chars=0,
                    max_chars=plan.max_chars,
                    min_tables=plan.min_tables,
                    min_figures=plan.min_figures,
                )
                section_text[sec_key] = trimmed
        merged = _sanitize_output_text(_merge_sections_text(title, sections, section_text))

    if ensure_min and config.min_total_chars > 0 and sections:
        total_len = sum(_section_body_len(section_text.get(sec) or '') for sec in sections)
        if total_len < config.min_total_chars:
            max_loops = max(120, len(sections) * 30)
            i = 0
            while total_len < config.min_total_chars and i < max_loops:
                sec = sections[i % len(sections)]
                if _is_reference_section(_section_title(sec) or sec):
                    i += 1
                    continue
                extra = _plan_point_paragraph(sec, plan_map.get(sec), i + 1) or _generic_fill_paragraph(sec, idx=i + 1)
                if extra:
                    current = (section_text.get(sec) or '').strip()
                    section_text[sec] = (current + '\n\n' + extra).strip() if current else extra
                    total_len += len(re.sub(r'\s+', '', extra))
                i += 1
            merged = _sanitize_output_text(_merge_sections_text(title, sections, section_text))

        # Final safety: ensure post-sanitize length meets target.
        body_len = _doc_body_len(merged)
        if body_len < config.min_total_chars:
            max_loops = max(60, len(sections) * 12)
            i = 0
            while body_len < config.min_total_chars and i < max_loops:
                sec = sections[i % len(sections)]
                if _is_reference_section(_section_title(sec) or sec):
                    i += 1
                    continue
                extra = _plan_point_paragraph(sec, plan_map.get(sec), i + 1) or _generic_fill_paragraph(sec, idx=i + 1)
                if extra:
                    current = (section_text.get(sec) or '').strip()
                    section_text[sec] = (current + '\n\n' + extra).strip() if current else extra
                    merged = _sanitize_output_text(_merge_sections_text(title, sections, section_text))
                    body_len = _doc_body_len(merged)
                i += 1

    merged = _strip_disallowed_sections_text(merged)
    if not re.search(r"(?m)^##\s+.+$", merged):
        fallback_sections = [
            "Introduction",
            "Requirement Analysis",
            "Overall Design",
            "Data Design",
            "Testing and Results",
            "Conclusion",
            "References",
        ]
        fallback_text: dict[str, str] = {}
        for sec in fallback_sections:
            if _is_reference_section(sec):
                lines = _format_reference_items(reference_sources or [])
                fallback_text[sec] = "\n".join(lines).strip()
            else:
                fallback_text[sec] = _generic_fill_paragraph(sec, idx=1)
        merged = _sanitize_output_text(_merge_sections_text(title, fallback_sections, fallback_text))
    merged = _strip_ack_sections_text(merged, allow_ack=wants_ack)
    merged = _clean_generated_text(merged)
    merged = _normalize_final_output(merged, expected_sections=sections)
    if config.max_total_chars and config.max_total_chars > 0:
        merged = _trim_total_chars(merged, int(config.max_total_chars))
    problems = _light_self_check(text=merged, sections=sections, target_chars=total_chars, evidence_enabled=evidence_enabled, reference_sources=reference_sources)
    if not agg_recorded:
        _record_phase_timing(run_id, {"phase": "AGGREGATE", "event": "end", "duration_s": time.time() - agg_start_ts})
        _record_phase_timing(run_id, {"phase": "TOTAL", "event": "end", "duration_s": time.time() - run_start_ts})
        agg_recorded = True
    yield {"event": "state", "name": "AGGREGATE", "phase": "end"}
    yield {"event": "final", "text": merged, "problems": problems}







def _compute_section_targets(*, sections: list[str], base_min_paras: int, total_chars: int) -> dict[str, SectionTargets]:
    weights = _load_section_weights()
    out: dict[str, SectionTargets] = {}
    total_weight = 0.0
    per_sec_weight: dict[str, float] = {}
    for sec in sections:
        title = _section_title(sec) or sec
        w = weights.get(title)
        if w is None:
            w = _guess_section_weight(title)
        per_sec_weight[sec] = max(0.2, float(w))
        total_weight += per_sec_weight[sec]
    total_weight = total_weight or max(1.0, float(len(sections)))
    for sec in sections:
        title = (_section_title(sec) or sec).strip()
        share = int(round(float(total_chars) * (per_sec_weight.get(sec, 1.0) / total_weight))) if total_chars > 0 else 0
        min_chars = max(220, int(share * 0.7)) if share > 0 else 800
        max_chars = _max_chars_for_section(title)
        min_tables = 1 if "结果" in title or "数据" in title else 0
        min_figures = 1 if "架构" in title or "流程" in title else 0
        out[sec] = SectionTargets(
            weight=per_sec_weight.get(sec, 1.0),
            min_paras=base_min_paras,
            min_chars=min_chars,
            max_chars=max_chars,
            min_tables=min_tables,
            min_figures=min_figures,
        )
    return out


class ModelPool:
    def __init__(self, models: list[str]) -> None:
        self._models = [m for m in (models or []) if m]
        self._lock = threading.Lock()
        self._i = 0

    def next(self) -> str:
        with self._lock:
            if not self._models:
                return ""
            m = self._models[self._i % len(self._models)]
            self._i += 1
            return m


@dataclass(frozen=True)
class SectionTargets:
    weight: float
    min_paras: int
    min_chars: int
    max_chars: int
    min_tables: int
    min_figures: int


@dataclass(frozen=True)
class PlanSection:
    title: str
    target_chars: int
    min_chars: int
    max_chars: int
    min_tables: int
    min_figures: int
    key_points: list[str]
    figures: list[dict]
    tables: list[dict]
    evidence_queries: list[str]





def _generate_section_stream(
    *,
    base_url: str,
    model: str,
    title: str,
    section: str,
    parent_section: str,
    instruction: str,
    analysis_summary: str,
    evidence_summary: str,
    allowed_urls: list[str],
    plan_hint: str,
    min_paras: int,
    min_chars: int,
    max_chars: int,
    min_tables: int,
    min_figures: int,
    out_queue: queue.Queue[dict],
    reference_items: list[dict],
    text_store: TextStore | None,
) -> str:
    client = OllamaClient(base_url=base_url, model=model, timeout_s=_section_timeout_s())
    table_hint = ""
    fig_hint = ""
    if min_tables > 0 or section in {"结果", "数据分析", "Results"}:
        table_hint = "\nPlease include at least one table (use table blocks)."
    if min_figures > 0:
        fig_hint = "\nPlease include at least one figure (use figure blocks)."

    sec_name = (_section_title(section) or section).strip()
    is_reference = _is_reference_section(sec_name)
    rag_context = _maybe_rag_context(instruction=instruction, section=sec_name)
    ref_items = reference_items or []
    section_id = _normalize_section_id(section)

    if is_reference and ref_items:
        lines = _format_reference_items(ref_items)
        text = "\n".join([ln for ln in lines if ln.strip()]).strip()
        if text:
            block_id = text_store.put_text(text) if text_store else ""
            payload = {"event": "section", "phase": "delta", "section": section, "delta": text, "block_type": "reference"}
            if block_id:
                payload["block_id"] = block_id
            out_queue.put(payload)
        return text

    config = get_prompt_config("writer")
    system, user = PromptBuilder.build_writer_prompt(
        section_title=sec_name,
        plan_hint=plan_hint or "",
        doc_title=title,
        analysis_summary=analysis_summary or instruction,
        section_id=section_id,
        previous_content=None,
        rag_context=rag_context
    )
    if table_hint:
        system += f"{table_hint}"
    if fig_hint:
        system += f"{fig_hint}"
    if ref_items:
        system += "\nUse bracket citations like [1]; citation numbers must come from the available source list.\n"
        user += "\nAvailable sources (cite by number):\n" + "\n".join(
            [f"[{i+1}] {str(s.get('title') or s.get('url') or s.get('id') or '').strip()} {str(s.get('url') or '').strip()}".strip() for i, s in enumerate(ref_items[:12])]
        ) + "\n\n"
    num_predict = _predict_num_tokens(min_chars=min_chars, max_chars=max_chars, is_reference=is_reference)
    deadline = time.time() + _section_timeout_s()
    txt = _stream_structured_blocks(
        client=client,
        system=system,
        user=user,
        out_queue=out_queue,
        section=section,
        section_id=section_id,
        is_reference=is_reference,
        num_predict=num_predict,
        deadline=deadline,
        strict_json=True,
        text_store=text_store,
    )
    out = _postprocess_section(
        section,
        txt,
        min_paras=min_paras,
        min_chars=min_chars,
        max_chars=max_chars,
        min_tables=min_tables,
        min_figures=min_figures,
    )
    if ref_items and not is_reference and not re.search(r"\[\d+\]", out):
        out = out.rstrip() + " [1]"
    return out





def _normalize_final_output(text: str, *, expected_sections: list[str] | None = None) -> str:
    cleaned = _strip_markdown_noise(text or "")
    cleaned = re.sub(r"(?m)^(#{1,3}\s+.+?)\s*#+\s*$", r"\1", cleaned)
    cleaned = re.sub(r"(?m)^\s*#+\s*$", "", cleaned)
    parsed = parse_report_text(cleaned)
    expected: list[tuple[int, str]] = []
    if expected_sections:
        for sec in expected_sections:
            lvl, title = _split_section_token(sec)
            clean = _clean_outline_title(title)
            if not clean:
                continue
            if clean in _DISALLOWED_SECTIONS or clean in _ACK_SECTIONS:
                continue
            if _is_reference_section(clean):
                expected.append((1, "参考文献"))
                continue
            lvl_i = 2 if lvl >= 3 else 1
            expected.append((lvl_i, clean))
    expected_idx = 0

    out_blocks: list[DocBlock] = []
    skip_level: int | None = None
    saw_h1 = False
    for b in parsed.blocks:
        if b.type == "heading":
            lvl = int(b.level or 1)
            if skip_level is not None and lvl <= skip_level:
                skip_level = None
            if skip_level is not None:
                continue
            title_raw = (b.text or "").strip()
            title = _clean_section_title(title_raw)
            if not title:
                skip_level = lvl
                continue
            if title in _DISALLOWED_SECTIONS or title in _ACK_SECTIONS:
                skip_level = lvl
                continue
            if lvl <= 1:
                if not saw_h1:
                    saw_h1 = True
                    title = _normalize_title_line(title)
                    lvl = 1
                else:
                    lvl = 2
            else:
                if expected:
                    if expected_idx >= len(expected):
                        continue
                    exp_lvl, exp_title = expected[expected_idx]
                    expected_idx += 1
                    title = exp_title
                    lvl = exp_lvl
                else:
                    lvl = 3 if lvl >= 3 else 2
            out_blocks.append(DocBlock(type="heading", level=lvl, text=title))
            continue
        if skip_level is not None:
            continue
        out_blocks.append(b)
    if not any(b.type == "heading" and int(b.level or 0) == 1 for b in out_blocks):
        title = _normalize_title_line(parsed.title or _default_title())
        out_blocks.insert(0, DocBlock(type="heading", level=1, text=title))
    return _blocks_to_doc_text(out_blocks)





def _ensure_section_minimums_stream(
    *,
    base_url: str,
    model: str,
    title: str,
    section: str,
    parent_section: str,
    instruction: str,
    analysis_summary: str,
    evidence_summary: str,
    allowed_urls: list[str],
    plan_hint: str,
    draft: str,
    min_paras: int,
    min_chars: int,
    max_chars: int,
    min_tables: int,
    min_figures: int,
    out_queue: queue.Queue[dict],
) -> str:
    return graph_section_draft_domain.ensure_section_minimums_stream(
        base_url=base_url,
        model=model,
        title=title,
        section=section,
        parent_section=parent_section,
        instruction=instruction,
        analysis_summary=analysis_summary,
        evidence_summary=evidence_summary,
        allowed_urls=allowed_urls,
        plan_hint=plan_hint,
        draft=draft,
        min_paras=min_paras,
        min_chars=min_chars,
        max_chars=max_chars,
        min_tables=min_tables,
        min_figures=min_figures,
        out_queue=out_queue,
        postprocess_section=_postprocess_section,
        stream_structured_blocks=_stream_structured_blocks,
        normalize_section_id=_normalize_section_id,
        predict_num_tokens=lambda min_chars, max_chars, is_reference: _predict_num_tokens(
            min_chars=min_chars,
            max_chars=max_chars,
            is_reference=is_reference,
        ),
        is_reference_section=_is_reference_section,
        section_timeout_s=_section_timeout_s,
        ollama_client_cls=OllamaClient,
    )


