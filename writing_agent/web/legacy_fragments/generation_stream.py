"""Legacy stream generation endpoint runtime."""

from __future__ import annotations

import json
import time
from collections.abc import Iterable
from typing import Any

from fastapi.responses import StreamingResponse

from writing_agent.llm.factory import get_provider_snapshot
from writing_agent.v2 import final_validator
from writing_agent.web.domains import route_graph_metrics_domain
from writing_agent.workflows import GenerateStreamDeps, GenerateStreamRequest, run_generate_stream_graph_with_fallback


def _app_v2():
    from writing_agent.web import app_v2

    return app_v2


def _sse(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _single_pass_generate_stream(*args, **kwargs):
    return _app_v2()._single_pass_generate_stream(*args, **kwargs)


def _ensure_ollama_ready_iter():
    return _app_v2()._ensure_ollama_ready_iter()


def _drain_single_pass_stream(stream: Iterable[dict[str, Any]]) -> tuple[str, list[dict[str, Any]]]:
    events: list[dict[str, Any]] = []
    final_text = ""
    for raw in stream:
        ev = dict(raw or {}) if isinstance(raw, dict) else {}
        events.append(ev)
        if str(ev.get("event") or "") == "result":
            final_text = str(ev.get("text") or "")
    return final_text, events


def _provider_mode_required_sections(session) -> list[str]:
    outline = list(getattr(session, "template_outline", []) or [])
    out: list[str] = []
    for item in outline:
        if isinstance(item, (list, tuple)) and len(item) >= 2:
            title = str(item[1] or "").strip()
            if title:
                out.append(title)
    if out:
        return out
    return [str(x).strip() for x in (getattr(session, "template_required_h2", []) or []) if str(x).strip()]


def _should_try_single_pass_provider_mode(*, session, compose_mode: str, resume_sections: list[str], base_text: str) -> bool:
    app_v2 = _app_v2()
    raw = str(app_v2.os.environ.get("WRITING_AGENT_PREFER_SINGLE_PASS_RESPONSES", "1") or "1").strip().lower()
    if raw not in {"1", "true", "yes", "on"}:
        return False
    if resume_sections or str(compose_mode or "").strip().lower() == "continue" or str(base_text or "").strip():
        return False
    prefs = dict(getattr(session, "generation_prefs", {}) or {})
    profile = str(prefs.get("quality_profile") or "").strip().lower()
    if profile and profile != "academic_cnki_default":
        return False
    snapshot = get_provider_snapshot()
    return str(snapshot.get("provider") or "").strip().lower() == "openai" and str(snapshot.get("wire_api") or "").strip().lower() == "responses"


def _try_single_pass_provider_mode_stream(
    *,
    session,
    instruction: str,
    raw_instruction: str,
    base_text: str,
    target_chars: int,
) -> tuple[str, dict[str, Any]] | None:
    app_v2 = _app_v2()
    final_text, _events = _drain_single_pass_stream(
        _single_pass_generate_stream(
            session,
            instruction=instruction,
            current_text=base_text,
            target_chars=target_chars,
        )
    )
    if not final_text or app_v2._looks_like_prompt_echo(final_text, raw_instruction):
        return None
    final_text = app_v2._postprocess_output_text(
        session,
        final_text,
        raw_instruction,
        current_text=base_text,
        base_text=base_text,
    )
    validation = final_validator.validate_final_document(
        title=str(app_v2._extract_title(final_text) or getattr(session, "title", "") or ""),
        text=final_text,
        sections=_provider_mode_required_sections(session),
        problems=list(app_v2._check_generation_quality(final_text, target_chars)),
    )
    if not bool(validation.get("passed")):
        return None
    graph_meta = {
        "path": "single_pass_provider_mode_stream",
        "engine": "single_pass",
        "route_id": "provider_compatibility",
        "route_entry": "single_pass_stream",
        "engine_failover": False,
        "terminal_status": "success",
        "failure_reason": "",
        "needs_review": False,
        "quality_snapshot": {
            "single_pass_provider_mode": True,
            "provider": get_provider_snapshot(),
            "final_validator": validation,
        },
    }
    payload = {
        "text": final_text,
        "problems": [],
        "doc_ir": app_v2._safe_doc_ir_payload(final_text),
        "graph_meta": graph_meta,
        "trace_context": {"route_path": "single_pass_provider_mode_stream"},
    }
    return final_text, payload


def _drive_ready(value):
    if isinstance(value, tuple):
        return value
    iterator = iter(value)
    while True:
        try:
            note = next(iterator)
        except StopIteration as exc:
            return exc.value or (True, "")
        yield _sse("delta", {"delta": f"model preparing: {note}"})


async def api_generate_stream(doc_id: str, request) -> StreamingResponse:
    app_v2 = _app_v2()
    session = app_v2.store.get(doc_id)
    if session is None:
        raise app_v2.HTTPException(status_code=404, detail="document not found")
    data = await request.json()
    from writing_agent.web.services.generation_service import GenerationService

    service = GenerationService()
    req = service._parse_generate_payload(app_v2, data, session=session)
    raw_instruction = str(req["raw_instruction"] or "").strip()
    if not raw_instruction:
        raise app_v2.HTTPException(status_code=400, detail="instruction required")

    token = app_v2._try_begin_doc_generation_with_wait(doc_id, mode="stream")
    if not token:
        raise app_v2.HTTPException(status_code=409, detail=app_v2._generation_busy_message(doc_id))

    def _iter():
        final_text = ""
        try:
            compose_instruction = service._build_generation_instruction(
                app_v2=app_v2,
                session=session,
                raw_instruction=raw_instruction,
                compose_mode=req["compose_mode"],
                resume_sections=req["resume_sections"],
                cursor_anchor=req["cursor_anchor"],
            )
            base_text = "" if req["compose_mode"] == "overwrite" else (req["current_text"] or session.doc_text or "")

            format_only = app_v2._try_handle_format_only_request(
                session=session,
                instruction=raw_instruction,
                base_text=base_text,
                compose_mode=req["compose_mode"],
                selection=req["selection_text"],
            )
            if format_only is not None:
                payload = {"ok": 1, **format_only}
                yield _sse("final", payload)
                return

            if not req["resume_sections"]:
                quick_edit = app_v2._try_quick_edit(base_text, raw_instruction, bool(req["confirm_apply"]))
                if quick_edit:
                    payload = {
                        "text": base_text,
                        "problems": [],
                        "doc_ir": app_v2._safe_doc_ir_payload(base_text),
                        "delta": quick_edit.note,
                    }
                    if not quick_edit.requires_confirmation:
                        out = service._build_shortcut_result(
                            app_v2=app_v2,
                            session=session,
                            text=quick_edit.text,
                            instruction=raw_instruction,
                            base_text=base_text,
                        )
                        payload.update(out)
                    yield _sse("final", payload)
                    return

            analysis_quick = app_v2._run_message_analysis(session, compose_instruction, quick=True)
            if not req["resume_sections"]:
                ai_edit = app_v2._try_ai_intent_edit(
                    base_text,
                    raw_instruction,
                    analysis_quick,
                    bool(req["confirm_apply"]),
                )
                if ai_edit:
                    if ai_edit.requires_confirmation:
                        yield _sse(
                            "final",
                            {
                                "text": base_text,
                                "problems": [],
                                "doc_ir": app_v2._safe_doc_ir_payload(base_text),
                                "note": ai_edit.note,
                                "requires_confirmation": True,
                                "confirmation_reason": ai_edit.confirmation_reason,
                                "risk_level": ai_edit.risk_level,
                            },
                        )
                        return
                    out = service._build_shortcut_result(
                        app_v2=app_v2,
                        session=session,
                        text=ai_edit.text,
                        instruction=raw_instruction,
                        base_text=base_text,
                    )
                    out["note"] = ai_edit.note
                    yield _sse("final", out)
                    return

            revision_status: dict[str, object] = {}
            if app_v2._should_route_to_revision(raw_instruction, base_text, analysis_quick):
                def _capture_revision_status(payload: dict[str, object]) -> None:
                    if isinstance(payload, dict):
                        revision_status.update(payload)

                revised = app_v2._try_revision_edit(
                    session=session,
                    instruction=raw_instruction,
                    text=base_text,
                    selection=req["selection_payload"],
                    analysis=analysis_quick,
                    context_policy=req["context_policy"],
                    report_status=_capture_revision_status,
                )
                if revision_status:
                    yield _sse("revision_status", dict(revision_status))
                if revised:
                    updated_text, note = revised
                    updated_text = app_v2._postprocess_output_text(
                        session,
                        updated_text,
                        raw_instruction,
                        current_text=base_text,
                        base_text=base_text,
                    )
                    app_v2._set_doc_text(session, updated_text)
                    app_v2._auto_commit_version(session, "auto: after update")
                    app_v2.store.put(session)
                    yield _sse(
                        "final",
                        {
                            "text": updated_text,
                            "problems": [],
                            "doc_ir": session.doc_ir or app_v2._safe_doc_ir_payload(updated_text),
                            "note": note,
                            "revision_meta": dict(revision_status) if revision_status else {},
                        },
                    )
                    return

            target_chars = app_v2._resolve_target_chars(session.formatting or {}, session.generation_prefs or {})
            if target_chars <= 0:
                target_chars = app_v2._extract_target_chars_from_instruction(raw_instruction)
            instruction = app_v2._augment_instruction(
                compose_instruction,
                formatting=session.formatting or {},
                generation_prefs=session.generation_prefs or {},
            )

            if _should_try_single_pass_provider_mode(
                session=session,
                compose_mode=req["compose_mode"],
                resume_sections=req["resume_sections"],
                base_text=base_text,
            ):
                provider_mode = _try_single_pass_provider_mode_stream(
                    session=session,
                    instruction=instruction,
                    raw_instruction=raw_instruction,
                    base_text=base_text,
                    target_chars=target_chars,
                )
                if provider_mode is not None:
                    final_text, payload = provider_mode
                    app_v2._set_doc_text(session, final_text)
                    app_v2._auto_commit_version(session, "auto: after update")
                    app_v2.store.put(session)
                    yield _sse("final", payload)
                    return

            yield _sse("delta", {"delta": "model preparing..."})
            ready = yield from _drive_ready(app_v2._ensure_ollama_ready_iter())
            ok, msg = ready if isinstance(ready, tuple) else (True, "")
            if not ok:
                yield _sse("error", {"message": str(msg or "model provider not ready")})
                return

            cfg = app_v2.GenerateConfig(workers=1, min_total_chars=target_chars if target_chars > 0 else 0, max_total_chars=0)
            trace_context: dict[str, object] = {}
            truncate_reason_codes: set[str] = set()
            route_metric_meta: dict[str, str] = {}

            def _with_terminal(payload: dict[str, Any]) -> dict[str, Any]:
                out = dict(payload or {})
                out.setdefault("trace_context", dict(trace_context))
                return out

            def _with_reason_codes(payload: dict[str, Any]) -> dict[str, Any]:
                out = dict(payload or {})
                if truncate_reason_codes:
                    out["truncate_reason_codes"] = sorted(truncate_reason_codes)
                out.setdefault("trace_context", dict(trace_context))
                return out

            def _record_metric(event: str, **kwargs: Any) -> None:
                route_graph_metrics_domain.record_route_graph_metric(event, phase="generate_stream", **kwargs)

            stream = run_generate_stream_graph_with_fallback(
                request=GenerateStreamRequest(
                    session=session,
                    raw_instruction=raw_instruction,
                    instruction=instruction,
                    current_text=base_text,
                    graph_current_text=base_text,
                    compose_mode=req["compose_mode"],
                    resume_sections=req["resume_sections"],
                    plan_confirm=req["plan_confirm"],
                    cfg=cfg,
                    target_chars=target_chars,
                    required_h2=list(req["resume_sections"]) if req["resume_sections"] else list(session.template_required_h2 or []),
                    required_outline=[] if req["resume_sections"] else list(session.template_outline or []),
                    expand_outline=bool((session.generation_prefs or {}).get("expand_outline", False)),
                    stall_s=float(app_v2.os.environ.get("WRITING_AGENT_STREAM_EVENT_TIMEOUT_S", "90")),
                    overall_s=float(app_v2.os.environ.get("WRITING_AGENT_STREAM_MAX_S", "180")),
                    section_stall_s=float(app_v2.os.environ.get("WRITING_AGENT_STREAM_SECTION_STALL_S", "0") or 0),
                    start_ts=time.time(),
                    trace_context=trace_context,
                    truncate_reason_codes=truncate_reason_codes,
                    route_metric_meta=route_metric_meta,
                ),
                deps=GenerateStreamDeps(
                    environ=app_v2.os.environ,
                    emit=_sse,
                    with_terminal=_with_terminal,
                    with_reason_codes=_with_reason_codes,
                    record_route_metric=_record_metric,
                    record_stream_timing=app_v2._record_stream_timing,
                    extract_error_code=route_graph_metrics_domain.extract_error_code,
                    should_inject_route_graph_failure=route_graph_metrics_domain.should_inject_route_graph_failure,
                    run_generate_graph_dual_engine=getattr(app_v2, "run_generate_graph_dual_engine", None),
                    run_generate_graph=app_v2.run_generate_graph,
                    iter_with_timeout=app_v2._iter_with_timeout,
                    postprocess_output_text=app_v2._postprocess_output_text,
                    safe_doc_ir_payload=app_v2._safe_doc_ir_payload,
                    single_pass_generate_stream=app_v2._single_pass_generate_stream,
                    check_generation_quality=app_v2._check_generation_quality,
                    log_graph_error=lambda exc: app_v2.logger.warning("stream graph failed: %s", exc),
                ),
            )
            try:
                while True:
                    yield next(stream)
            except StopIteration as exc:
                result = exc.value if isinstance(exc.value, dict) else {}
                final_text = str(result.get("final_text") or "")
            if final_text:
                app_v2._set_doc_text(session, final_text)
                app_v2._auto_commit_version(session, "auto: after update")
                app_v2.store.put(session)
        finally:
            app_v2._finish_doc_generation(doc_id, token)

    return StreamingResponse(_iter(), media_type="text/event-stream")


def install(g: dict) -> None:
    g["api_generate_stream"] = api_generate_stream
