"""App V2 Generate Stream Runtime module.

This module belongs to `writing_agent.web` in the writing-agent codebase.
"""

from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import StreamingResponse

from writing_agent.workflows import (
    GenerateStreamDeps,
    GenerateStreamRequest,
    run_generate_stream_graph_with_fallback,
)
from writing_agent.workflows.orchestration_backend import record_orchestration_metric
from writing_agent.web.domains import route_graph_metrics_domain


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
    selection_payload = data.get("selection")
    selection_text = (
        str(selection_payload.get("text") or "")
        if isinstance(selection_payload, dict)
        else str(selection_payload or "")
    )
    context_policy = data.get("context_policy")
    compose_mode = _normalize_compose_mode(data.get("compose_mode"))
    resume_sections = _normalize_resume_sections(data.get("resume_sections"))
    cursor_anchor = str(data.get("cursor_anchor") or "").strip()
    confirm_apply = bool(data.get("confirm_apply") is True)
    plan_confirm_raw = data.get("plan_confirm")
    plan_confirm_obj = plan_confirm_raw if isinstance(plan_confirm_raw, dict) else {}
    plan_decision = str(plan_confirm_obj.get("decision") or "").strip().lower()
    if plan_decision in {"stop", "terminate", "cancel", "reject"}:
        plan_decision = "interrupted"
    elif plan_decision != "interrupted":
        plan_decision = "approved"
    try:
        plan_score = int(plan_confirm_obj.get("score") or 0)
    except Exception:
        plan_score = 0
    plan_confirm = {
        "decision": plan_decision,
        "score": max(0, min(5, plan_score)),
        "note": str(plan_confirm_obj.get("note") or "").strip()[:300],
    }
    if not raw_instruction:
        raise HTTPException(status_code=400, detail="instruction required")
    stream_token = _try_begin_doc_generation_with_wait(doc_id, mode="stream")
    if not stream_token:
        raise HTTPException(status_code=409, detail=_generation_busy_message(doc_id))
    def emit(event: str, payload: dict) -> str:
        _touch_doc_generation(doc_id, stream_token)
        return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
    def iter_events():
        truncate_reason_codes: set[str] = set()
        trace_context: dict[str, object] = {
            "route_path": "",
            "fallback_trigger": "",
            "fallback_recovered": False,
        }

        def _with_reason_codes(payload: dict) -> dict:
            out = dict(payload or {})
            if truncate_reason_codes:
                out["truncate_reason_codes"] = sorted(truncate_reason_codes)
            return out

        def _with_trace_context(payload: dict) -> dict:
            out = dict(payload or {})
            merged_trace = dict(trace_context)
            existing_trace = out.get("trace_context")
            if isinstance(existing_trace, dict):
                merged_trace.update({k: v for k, v in existing_trace.items() if v not in (None, "")})
            out["trace_context"] = merged_trace
            meta = out.get("graph_meta")
            if isinstance(meta, dict):
                merged_meta = dict(meta)
                meta_trace = merged_meta.get("trace_context")
                if isinstance(meta_trace, dict):
                    merged_trace.update({k: v for k, v in meta_trace.items() if v not in (None, "")})
                merged_meta["trace_context"] = dict(merged_trace)
                out["graph_meta"] = merged_meta
            return out

        def _with_terminal(payload: dict) -> dict:
            out = _with_trace_context(dict(payload or {}))
            meta = out.get("graph_meta") if isinstance(out.get("graph_meta"), dict) else {}
            status_raw = str(out.get("status") or meta.get("terminal_status") or "success").strip().lower()
            status = status_raw if status_raw in {"success", "failed", "interrupted"} else "success"
            out["status"] = status
            out["failure_reason"] = str(out.get("failure_reason") or meta.get("failure_reason") or "")
            snapshot = out.get("quality_snapshot")
            if not isinstance(snapshot, dict):
                snapshot = meta.get("quality_snapshot")
            out["quality_snapshot"] = dict(snapshot) if isinstance(snapshot, dict) else {}
            return _with_reason_codes(out)

        base_text = "" if compose_mode == "overwrite" else (current_text or session.doc_text or "")
        format_only = _try_handle_format_only_request(
            session=session,
            instruction=raw_instruction,
            base_text=base_text,
            compose_mode=compose_mode,
            selection=selection_text,
        )
        if format_only is not None:
            yield emit("final", _with_terminal(format_only))
            return
        if str(plan_confirm.get("decision") or "").strip().lower() == "interrupted":
            interrupted_payload = {
                "text": base_text,
                "problems": ["plan_not_confirmed_by_user"],
                "doc_ir": _safe_doc_ir_payload(base_text),
                "status": "interrupted",
                "failure_reason": "plan_not_confirmed_by_user",
                "quality_snapshot": {
                    "status": "interrupted",
                    "reason": "plan_not_confirmed_by_user",
                    "problem_count": 1,
                },
                "plan_feedback": {
                    "decision": "interrupted",
                    "score": int(plan_confirm.get("score") or 0),
                    "note": str(plan_confirm.get("note") or ""),
                },
            }
            yield emit("final", _with_terminal(interrupted_payload))
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
        base_text = "" if compose_mode == "overwrite" else (current_text or session.doc_text or "")
        has_existing = bool(str(session.doc_text or "").strip())
        compose_instruction = _apply_compose_mode_instruction(raw_instruction, compose_mode, has_existing=has_existing)
        if resume_sections:
            compose_instruction = _apply_resume_sections_instruction(
                compose_instruction,
                resume_sections,
                cursor_anchor=cursor_anchor,
            )
        if base_text.strip():
            if base_text != session.doc_text:
                _set_doc_text(session, base_text)
            _auto_commit_version(session, "auto: before update")
        quick_edit = None if resume_sections else _try_quick_edit(base_text, raw_instruction, confirm_apply)
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
            yield emit(
                "final",
                _with_terminal({"text": updated_text, "problems": [], "doc_ir": _safe_doc_ir_payload(updated_text)}),
            )
            return
        analysis_quick = _run_message_analysis(session, compose_instruction, quick=True)
        ai_edit = None if resume_sections else _try_ai_intent_edit(base_text, raw_instruction, analysis_quick, confirm_apply)
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
            yield emit(
                "final",
                _with_terminal({"text": updated_text, "problems": [], "doc_ir": _safe_doc_ir_payload(updated_text)}),
            )
            return
        if _should_route_to_revision(raw_instruction, base_text, analysis_quick):
            summary = "Detected revision instruction and switched to quick edit flow."
            yield emit("analysis", {"summary": summary, "steps": ["locate target scope", "apply rewrite", "validate structure"], "missing": []})
            revision_status: dict[str, object] = {}

            def _capture_revision_status(payload: dict[str, object]) -> None:
                if isinstance(payload, dict):
                    revision_status.update(payload)

            revised = _try_revision_edit(
                session=session,
                instruction=raw_instruction,
                text=base_text,
                selection=selection_payload,
                analysis=analysis_quick,
                context_policy=context_policy,
                report_status=_capture_revision_status,
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
                payload = {"text": updated_text, "problems": [], "doc_ir": _safe_doc_ir_payload(updated_text)}
                if revision_status:
                    payload["revision_meta"] = revision_status
                yield emit("final", _with_terminal(payload))
                return
            if revision_status:
                yield emit("revision_status", revision_status)
            yield emit("delta", {"delta": "fast revise failed, fallback to full generation."})
        if _should_use_fast_generate(raw_instruction, target_chars, session.generation_prefs or {}):
            fast_done = False
            try:
                instruction = _augment_instruction(
                    compose_instruction,
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
                    failover_meta = {
                        "path": "single_pass_stream",
                        "trace_id": "",
                        "engine": "single_pass",
                        "route_id": "",
                        "route_entry": "",
                        "engine_failover": True,
                        "terminal_status": "interrupted",
                        "needs_review": True,
                    }
                    if prompt_trace:
                        failover_meta["prompt_trace"] = prompt_trace[-24:]
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
                            _with_terminal(
                                {"text": final_text, "problems": quality_issues, "doc_ir": _safe_doc_ir_payload(final_text)}
                            ),
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
            lambda: _run_message_analysis(session, compose_instruction),
            analysis_timeout,
            _normalize_analysis({}, compose_instruction),
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
            analysis = _normalize_analysis({}, compose_instruction)
        analysis_instruction = _compose_analysis_input(compose_instruction, analysis)
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
                # Keep only a lower bound to avoid truncating complete paragraphs at tail.
                max_total_chars=0,
            )
        else:
            cfg = GenerateConfig(
                workers=int(os.environ.get("WRITING_AGENT_WORKERS", "12")),  # tuned from 10 -> 12
            )
        final_text: str | None = None
        route_metric_meta: dict[str, str] = {"route_id": "", "route_entry": "", "engine": ""}

        def _route_elapsed_ms() -> float:
            return max(0.0, (time.time() - start_ts) * 1000.0)

        def _record_route_metric(
            event: str,
            *,
            path: str,
            fallback_triggered: bool | None = None,
            fallback_recovered: bool | None = None,
            error_code: str = "",
        ) -> None:
            record_orchestration_metric(
                route_graph_metrics_domain.record_route_graph_metric,
                event=event,
                phase="generate_stream",
                path=path,
                meta=route_metric_meta,
                fallback_triggered=fallback_triggered,
                fallback_recovered=fallback_recovered,
                error_code=error_code,
                elapsed_ms=_route_elapsed_ms(),
                compose_mode=compose_mode,
                resume_sections=resume_sections,
            )

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
        expand_outline = bool((session.generation_prefs or {}).get("expand_outline", False))
        required_h2 = list(resume_sections) if resume_sections else list(session.template_required_h2 or [])
        required_outline = [] if resume_sections else list(session.template_outline or [])
        graph_current_text = "" if compose_mode == "overwrite" else (current_text or session.doc_text or "")

        def _log_graph_error(exc: Exception) -> None:
            try:
                log_path = Path(".data/logs/graph_error.log")
                log_path.parent.mkdir(parents=True, exist_ok=True)
                log_path.write_text(
                    f"{time.strftime('%Y-%m-%d %H:%M:%S')} graph_error: {exc}\n{traceback.format_exc()}\n",
                    encoding="utf-8",
                )
            except Exception:
                pass

        workflow_result = yield from run_generate_stream_graph_with_fallback(
            request=GenerateStreamRequest(
                session=session,
                raw_instruction=raw_instruction,
                instruction=instruction,
                current_text=current_text,
                graph_current_text=graph_current_text,
                compose_mode=compose_mode,
                resume_sections=resume_sections,
                plan_confirm=plan_confirm,
                cfg=cfg,
                target_chars=target_chars,
                required_h2=required_h2,
                required_outline=required_outline,
                expand_outline=expand_outline,
                stall_s=stall_s,
                overall_s=overall_s,
                section_stall_s=section_stall_s,
                start_ts=start_ts,
                trace_context=trace_context,
                truncate_reason_codes=truncate_reason_codes,
                route_metric_meta=route_metric_meta,
            ),
            deps=GenerateStreamDeps(
                environ=os.environ,
                emit=emit,
                with_terminal=_with_terminal,
                with_reason_codes=_with_reason_codes,
                record_route_metric=_record_route_metric,
                record_stream_timing=_record_stream_timing,
                extract_error_code=route_graph_metrics_domain.extract_error_code,
                should_inject_route_graph_failure=route_graph_metrics_domain.should_inject_route_graph_failure,
                run_generate_graph_dual_engine=globals().get("run_generate_graph_dual_engine"),
                run_generate_graph=run_generate_graph,
                iter_with_timeout=_iter_with_timeout,
                postprocess_output_text=_postprocess_output_text,
                safe_doc_ir_payload=_safe_doc_ir_payload,
                single_pass_generate_stream=_single_pass_generate_stream,
                check_generation_quality=_check_generation_quality,
                log_graph_error=_log_graph_error,
            ),
        )
        if isinstance(workflow_result, dict) and bool(workflow_result.get("stop")):
            return
        if isinstance(workflow_result, dict):
            final_text = workflow_result.get("final_text")
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

