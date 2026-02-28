"""App V2 Generate Stream Runtime module.

This module belongs to `writing_agent.web` in the writing-agent codebase.
"""

from __future__ import annotations


_BIND_SKIP_NAMES = {
    "__builtins__",
    "__cached__",
    "__doc__",
    "__file__",
    "__loader__",
    "__name__",
    "__package__",
    "__spec__",
    "_BIND_SKIP_NAMES",
    "bind",
    "api_generate_stream",
}


def bind(namespace: dict) -> None:
    for key, value in namespace.items():
        if key in _BIND_SKIP_NAMES:
            continue
        globals()[key] = value


async def api_generate_stream(doc_id: str, request: Request) -> StreamingResponse:
    session = store.get(doc_id)
    if session is None:
        raise HTTPException(status_code=404, detail="document not found")
    data = await request.json()
    raw_instruction = str(data.get("instruction") or "").strip()
    current_text = str(data.get("text") or "")
    selection = str(data.get("selection") or "")
    compose_mode = _normalize_compose_mode(data.get("compose_mode"))
    confirm_apply = bool(data.get("confirm_apply") is True)
    if not raw_instruction:
        raise HTTPException(status_code=400, detail="instruction required")
    stream_token = _try_begin_doc_generation_with_wait(doc_id, mode="stream")
    if not stream_token:
        raise HTTPException(status_code=409, detail=_generation_busy_message(doc_id))
    def emit(event: str, payload: dict) -> str:
        _touch_doc_generation(doc_id, stream_token)
        return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
    def iter_events():
        base_text = current_text or session.doc_text or ""
        format_only = _try_handle_format_only_request(
            session=session,
            instruction=raw_instruction,
            base_text=base_text,
            compose_mode=compose_mode,
            selection=selection,
        )
        if format_only is not None:
            yield emit("final", format_only)
            return
        yield emit("delta", {"delta": "model preparing..."})
        prep_queue: queue.Queue[str] = queue.Queue()
        result: dict[str, object] = {"ok": True, "msg": ""}
        def _prep_worker() -> None:
            nonlocal result
            try:
                ready_iter = _ensure_ollama_ready_iter()
                if isinstance(ready_iter, tuple):
                    ok, msg = ready_iter
                    result = {"ok": ok, "msg": msg}
                    return
                for note in ready_iter:
                    if note:
                        prep_queue.put(str(note))
                result = {"ok": True, "msg": ""}
            except Exception as e:
                result = {"ok": False, "msg": str(e)}
        prep_thread = threading.Thread(target=_prep_worker, daemon=True)
        prep_thread.start()
        last_emit = time.time()
        while prep_thread.is_alive() or not prep_queue.empty():
            try:
                note = prep_queue.get(timeout=1.0)
                if note:
                    yield emit("delta", {"delta": note})
                    last_emit = time.time()
            except queue.Empty:
                if time.time() - last_emit > 3:
                    yield emit("delta", {"delta": "model preparing..."})
                    last_emit = time.time()
        ok = bool(result.get("ok"))
        msg = str(result.get("msg") or "")
        if not ok:
            yield emit("error", {"message": msg or "model preparation failed"})
            return
        prefs = session.generation_prefs or {}
        fmt = session.formatting or {}
        target_chars = _resolve_target_chars(fmt, prefs)
        if target_chars <= 0:
            target_chars = _extract_target_chars_from_instruction(raw_instruction)
        base_text = current_text or session.doc_text or ""
        if base_text.strip():
            if base_text != session.doc_text:
                _set_doc_text(session, base_text)
            _auto_commit_version(session, "auto: before update")
        quick_edit = _try_quick_edit(base_text, raw_instruction, confirm_apply)
        if quick_edit:
            if quick_edit.requires_confirmation:
                yield emit(
                    "confirmation_required",
                    {
                        "note": quick_edit.note,
                        "requires_confirmation": True,
                        "confirmation_reason": quick_edit.confirmation_reason or "high_risk_edit",
                        "risk_level": quick_edit.risk_level,
                        "plan_source": quick_edit.source,
                        "operations_count": quick_edit.operations_count,
                        "confirmation_action": "confirm_apply",
                    },
                )
                return
            updated_text = quick_edit.text
            note = quick_edit.note
            updated_text = _postprocess_output_text(
                session,
                updated_text,
                raw_instruction,
                current_text=base_text,
                base_text=base_text,
            )
            _set_doc_text(session, updated_text)
            _auto_commit_version(session, "auto: after update")
            store.put(session)
            yield emit("delta", {"delta": note})
            yield emit("final", {"text": updated_text, "problems": [], "doc_ir": _safe_doc_ir_payload(updated_text)})
            return
        analysis_quick = _run_message_analysis(session, raw_instruction, quick=True)
        ai_edit = _try_ai_intent_edit(base_text, raw_instruction, analysis_quick, confirm_apply)
        if ai_edit:
            if ai_edit.requires_confirmation:
                yield emit(
                    "confirmation_required",
                    {
                        "note": ai_edit.note,
                        "requires_confirmation": True,
                        "confirmation_reason": ai_edit.confirmation_reason or "high_risk_edit",
                        "risk_level": ai_edit.risk_level,
                        "plan_source": ai_edit.source,
                        "operations_count": ai_edit.operations_count,
                        "confirmation_action": "confirm_apply",
                    },
                )
                return
            updated_text = ai_edit.text
            note = ai_edit.note
            updated_text = _postprocess_output_text(
                session,
                updated_text,
                raw_instruction,
                current_text=base_text,
                base_text=base_text,
            )
            _set_doc_text(session, updated_text)
            _auto_commit_version(session, "auto: after update")
            store.put(session)
            yield emit("delta", {"delta": note})
            yield emit("final", {"text": updated_text, "problems": [], "doc_ir": _safe_doc_ir_payload(updated_text)})
            return
        if _should_route_to_revision(raw_instruction, base_text, analysis_quick):
            summary = "Detected revision instruction and switched to quick edit flow."
            yield emit("analysis", {"summary": summary, "steps": ["locate target scope", "apply rewrite", "validate structure"], "missing": []})
            revised = _try_revision_edit(
                session=session,
                instruction=raw_instruction,
                text=base_text,
                selection=selection,
                analysis=analysis_quick,
            )
            if revised:
                updated_text, note = revised
                updated_text = _postprocess_output_text(
                    session,
                    updated_text,
                    raw_instruction,
                    current_text=base_text,
                    base_text=base_text,
                )
                _set_doc_text(session, updated_text)
                _auto_commit_version(session, "auto: after update")
                store.put(session)
                yield emit("delta", {"delta": note})
                yield emit("final", {"text": updated_text, "problems": [], "doc_ir": _safe_doc_ir_payload(updated_text)})
                return
            yield emit("delta", {"delta": "fast revise failed, fallback to full generation."})
        if _should_use_fast_generate(raw_instruction, target_chars, session.generation_prefs or {}):
            fast_done = False
            try:
                instruction = _augment_instruction(
                    raw_instruction,
                    formatting=session.formatting or {},
                    generation_prefs=session.generation_prefs or {},
                )
                # Use streaming version with heartbeat for better UX
                final_text = ""
                saw_stream_delta = False
                for event in _single_pass_generate_stream(
                    session,
                    instruction=instruction,
                    current_text=current_text,
                    target_chars=target_chars,
                ):
                    if event.get("event") == "heartbeat":
                        yield emit("delta", {"delta": event.get("message", "")})
                    elif event.get("event") == "section":
                        saw_stream_delta = True
                        yield emit("section", event)
                    elif event.get("event") == "result":
                        final_text = event.get("text", "")
                if final_text:
                    final_text = _postprocess_output_text(
                        session,
                        final_text,
                        raw_instruction,
                        current_text=current_text,
                    )
                    if not _looks_like_prompt_echo(final_text, raw_instruction):
                        # Check generation quality
                        quality_issues = _check_generation_quality(final_text, target_chars)
                        if not saw_stream_delta:
                            yield emit("section", {"section": "fast", "phase": "delta", "delta": final_text})
                        yield emit(
                            "final",
                            {"text": final_text, "problems": quality_issues, "doc_ir": _safe_doc_ir_payload(final_text)},
                        )
                        _set_doc_text(session, final_text)
                        _auto_commit_version(session, "auto: after update")
                        store.put(session)
                        fast_done = True
                    else:
                        yield emit("delta", {"delta": "fast generation result invalid, fallback to full generation."})
            except Exception:
                yield emit("delta", {"delta": "fast generation failed, fallback to full generation."})
            if fast_done:
                return
        analysis_timeout = float(os.environ.get("WRITING_AGENT_ANALYSIS_MAX_S", "20"))
        analysis_iter = _run_with_heartbeat(
            lambda: _run_message_analysis(session, raw_instruction),
            analysis_timeout,
            _normalize_analysis({}, raw_instruction),
            label="analysis in progress",
        )
        if isinstance(analysis_iter, tuple):
            analysis = analysis_iter
        else:
            analysis = None
            try:
                while True:
                    note = next(analysis_iter)
                    if note:
                        yield emit("delta", {"delta": str(note)})
            except StopIteration as e:
                analysis = e.value
        if analysis is None:
            analysis = _normalize_analysis({}, raw_instruction)
        analysis_instruction = _compose_analysis_input(raw_instruction, analysis)
        instruction = _augment_instruction(
            analysis_instruction,
            formatting=session.formatting or {},
            generation_prefs=session.generation_prefs or {},
        )
        # Auto-outline for common document types when no template outline is present.
        if not session.template_required_h2 and not session.template_outline:
            auto_outline = _default_outline_from_instruction(raw_instruction)
            if auto_outline:
                session.template_required_h2 = auto_outline
                store.put(session)
        summary = _summarize_analysis(raw_instruction, analysis)
        if isinstance(summary, dict):
            summary["raw"] = analysis
        yield emit("analysis", summary)
        prefs = session.generation_prefs or {}
        fmt = session.formatting or {}
        target_chars = _resolve_target_chars(fmt, prefs)
        if target_chars <= 0:
            target_chars = _extract_target_chars_from_instruction(raw_instruction)
        if target_chars > 0:
            raw_margin = os.environ.get("WRITING_AGENT_TARGET_MARGIN", "").strip()
            try:
                margin = float(raw_margin) if raw_margin else 0.15
            except Exception:
                margin = 0.15
            margin = max(0.0, min(0.3, margin))
            internal_target = int(round(target_chars * (1.0 + margin)))
            cfg = GenerateConfig(
                workers=int(os.environ.get("WRITING_AGENT_WORKERS", "12")),  # tuned from 10 -> 12
                min_total_chars=internal_target,
                max_total_chars=internal_target,
            )
        else:
            cfg = GenerateConfig(
                workers=int(os.environ.get("WRITING_AGENT_WORKERS", "12")),  # tuned from 10 -> 12
            )
        final_text: str | None = None
        problems: list[str] = []
        overall_default_s, stall_default_s = _recommended_stream_timeouts()
        stall_s = float(os.environ.get("WRITING_AGENT_STREAM_EVENT_TIMEOUT_S", str(int(stall_default_s))))
        stall_s = max(stall_s, stall_default_s)
        overall_s = float(os.environ.get("WRITING_AGENT_STREAM_MAX_S", str(int(overall_default_s))))
        overall_s = max(overall_s, overall_default_s)
        overall_cap_raw = str(os.environ.get("WRITING_AGENT_STREAM_MAX_CAP_S", "360")).strip()
        stall_cap_raw = str(os.environ.get("WRITING_AGENT_STREAM_EVENT_TIMEOUT_CAP_S", "120")).strip()
        try:
            overall_cap_s = float(overall_cap_raw) if overall_cap_raw else 0.0
        except Exception:
            overall_cap_s = 360.0
        try:
            stall_cap_s = float(stall_cap_raw) if stall_cap_raw else 0.0
        except Exception:
            stall_cap_s = 120.0
        if overall_cap_s > 0:
            overall_s = min(overall_s, overall_cap_s)
        if stall_cap_s > 0:
            stall_s = min(stall_s, stall_cap_s)
        if overall_s > 0 and stall_s >= overall_s:
            stall_s = max(30.0, overall_s * 0.6)
        section_raw = os.environ.get("WRITING_AGENT_STREAM_SECTION_TIMEOUT_S", "").strip()
        section_stall_s = float(section_raw) if section_raw else 0.0
        if section_stall_s > 0 and section_stall_s < stall_s:
            section_stall_s = stall_s
        start_ts = time.time()
        max_gap_s = 0.0
        try:
            expand_outline = bool((session.generation_prefs or {}).get("expand_outline", False))
            gen = run_generate_graph(
                instruction=instruction,
                current_text=current_text,
                required_h2=list(session.template_required_h2 or []),
                required_outline=list(session.template_outline or []),
                expand_outline=expand_outline,
                config=cfg,
            )
            last_section_at: float | None = None
            last_event_at = start_ts
            for ev in _iter_with_timeout(gen, per_event=stall_s, overall=overall_s):
                now = time.time()
                gap = now - last_event_at
                if gap > max_gap_s:
                    max_gap_s = gap
                last_event_at = now
                if ev.get("event") == "final":
                    final_text = _postprocess_output_text(
                        session,
                        str(ev.get("text") or ""),
                        raw_instruction,
                        current_text=current_text,
                    )
                    problems = list(ev.get("problems") or [])
                    payload = dict(ev)
                    payload["text"] = final_text
                    payload["doc_ir"] = _safe_doc_ir_payload(final_text)
                    yield emit(payload.get("event", "message"), payload)
                    _record_stream_timing(total_s=time.time() - start_ts, max_gap_s=max_gap_s)
                    break
                yield emit(ev.get("event", "message"), ev)
                if ev.get("event") == "section" and ev.get("phase") == "delta":
                    last_section_at = time.time()
                if section_stall_s > 0:
                    if last_section_at is not None and time.time() - last_section_at > section_stall_s:
                        raise TimeoutError("section stalled")
        except Exception as e:
            try:
                log_path = Path(".data/logs/graph_error.log")
                log_path.parent.mkdir(parents=True, exist_ok=True)
                log_path.write_text(
                    f"{time.strftime('%Y-%m-%d %H:%M:%S')} graph_error: {e}\n{traceback.format_exc()}\n",
                    encoding="utf-8",
                )
            except Exception:
                pass
            # fallback to single-pass generation if streaming pipeline stalls
            try:
                # Use streaming version with heartbeat
                final_text = None
                saw_stream_delta = False
                for event in _single_pass_generate_stream(
                    session,
                    instruction=instruction,
                    current_text=current_text,
                    target_chars=target_chars,
                ):
                    if event.get("event") == "heartbeat":
                        yield emit("delta", {"delta": event.get("message", "")})
                    elif event.get("event") == "section":
                        saw_stream_delta = True
                        yield emit("section", event)
                    elif event.get("event") == "result":
                        final_text = event.get("text", "")
                if final_text:
                    final_text = _postprocess_output_text(
                        session,
                        final_text,
                        raw_instruction,
                        current_text=current_text,
                    )
                    # Check generation quality
                    quality_issues = _check_generation_quality(final_text, target_chars)
                    if not saw_stream_delta:
                        yield emit("section", {"section": "fallback", "phase": "delta", "delta": final_text})
                    yield emit(
                        "final",
                        {"text": final_text, "problems": quality_issues, "doc_ir": _safe_doc_ir_payload(final_text)},
                    )
                    _record_stream_timing(total_s=time.time() - start_ts, max_gap_s=max_gap_s)
            except Exception as ee:
                yield emit("error", {"message": f"generation failed: {e}; fallback failed: {ee}"})
        if final_text is None or len(final_text.strip()) < 20:
            # Fallback: single-pass generation to avoid empty output on stream failures.
            try:
                final_text = None
                saw_stream_delta = False
                for event in _single_pass_generate_stream(
                    session,
                    instruction=instruction,
                    current_text=current_text,
                    target_chars=target_chars,
                ):
                    if event.get("event") == "heartbeat":
                        yield emit("delta", {"delta": event.get("message", "")})
                    elif event.get("event") == "section":
                        saw_stream_delta = True
                        yield emit("section", event)
                    elif event.get("event") == "result":
                        final_text = event.get("text", "")
                if final_text:
                    final_text = _postprocess_output_text(
                        session,
                        final_text,
                        raw_instruction,
                        current_text=current_text,
                    )
                    # Check generation quality
                    quality_issues = _check_generation_quality(final_text, target_chars)
                    if not saw_stream_delta:
                        yield emit(
                            "section",
                            {"section": "fallback", "phase": "delta", "delta": final_text},
                        )
                    yield emit(
                        "final",
                        {"text": final_text, "problems": quality_issues, "doc_ir": _safe_doc_ir_payload(final_text)},
                    )
                    _record_stream_timing(total_s=time.time() - start_ts, max_gap_s=max_gap_s)
            except Exception as e:
                yield emit("error", {"message": f"生成失败：未得到正文且兜底失败：{e}"})
                return
        # Persist final text so refresh/reconnect keeps latest generated content.
        if final_text is not None:
            _set_doc_text(session, final_text)
            _auto_commit_version(session, "auto: after update")
            store.put(session)
    def guarded_events():
        try:
            yield from iter_events()
        finally:
            _finish_doc_generation(doc_id, stream_token)
    return StreamingResponse(
        guarded_events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
