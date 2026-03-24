"""Analysis and paradigm resolution helpers for runtime session orchestration."""

from __future__ import annotations

import os
import time


def _base():
    from writing_agent.v2 import graph_runner_runtime_session_domain as base

    return base


def _clarification_questions(analysis: dict, *, limit: int = 5) -> list[str]:
    return [
        str(x).strip()
        for x in (analysis.get("_clarification_questions") or [])
        if str(x).strip()
    ][:limit]


def _analysis_event_payload(analysis: dict) -> dict[str, object]:
    return {
        "event": "analysis",
        "topic": str(analysis.get("topic") or ""),
        "doc_type": str(analysis.get("doc_type") or ""),
        "audience": str(analysis.get("audience") or ""),
        "style": str(analysis.get("style") or ""),
        "keywords": [str(x).strip() for x in (analysis.get("keywords") or []) if str(x).strip()][:12],
        "must_include": [str(x).strip() for x in (analysis.get("must_include") or []) if str(x).strip()][:20],
        "constraints": [str(x).strip() for x in (analysis.get("constraints") or []) if str(x).strip()][:20],
        "confidence": float(analysis.get("_confidence_score") or 0.0),
        "schema_valid": bool(analysis.get("_schema_valid")),
        "needs_clarification": bool(analysis.get("_needs_clarification")),
        "clarification_questions": _clarification_questions(analysis),
    }


def _resolve_low_confidence_probe(
    runtime_api,
    *,
    instruction: str,
    analysis: dict,
    paradigm_decision: dict,
    analysis_fast_mode: str,
    required_outline,
    required_h2,
    build_final_event,
) -> dict[str, object]:
    result: dict[str, object] = {"events": [], "forced_sections": [], "selected_paradigm": "", "terminal_event": None}
    analysis_fast_forced = analysis_fast_mode in {"force", "always"}
    should_probe = (
        bool(paradigm_decision.get("low_confidence"))
        and (not analysis_fast_forced)
        and not bool(analysis.get("_synthesized"))
        and not required_outline
        and not required_h2
    )
    if not should_probe:
        return result

    primary = str(paradigm_decision.get("paradigm") or "").strip()
    secondary = str(paradigm_decision.get("runner_up") or "").strip()
    if (not primary) or (not secondary) or primary == secondary:
        return result

    probe = runtime_api._dual_outline_probe(
        instruction=instruction,
        analysis=analysis,
        primary_paradigm=primary,
        secondary_paradigm=secondary,
    )
    result["events"] = [
        {
            "event": "dual_outline_probe",
            "primary_paradigm": primary,
            "secondary_paradigm": secondary,
            "selected_paradigm": str(probe.get("selected_paradigm") or ""),
            "resolved": bool(probe.get("resolved")),
            "margin": float(probe.get("margin") or 0.0),
            "scores": dict(probe.get("scores") or {}),
            "reason": str(probe.get("reason") or ""),
        }
    ]
    if not bool(probe.get("resolved")):
        reason = "paradigm_low_confidence_unresolved"
        result["terminal_event"] = build_final_event(
            text="",
            problems=[reason],
            status="failed",
            failure_reason=reason,
            quality_snapshot={
                "status": "failed",
                "reason": reason,
                "paradigm": dict(paradigm_decision),
                "probe": dict(probe),
            },
            runtime_status="failed",
            runtime_failure_reason=reason,
            quality_passed=False,
            quality_failure_reason=reason,
        )
        return result

    result["forced_sections"] = [str(x).strip() for x in (probe.get("selected_outline") or []) if str(x).strip()]
    if result["forced_sections"]:
        result["selected_paradigm"] = str(probe.get("selected_paradigm") or primary)
    return result


def resolve_analysis_state(
    runtime_api,
    *,
    instruction: str,
    current_text: str,
    required_h2: list[str] | None,
    required_outline: list[tuple[int, str]] | None,
    local_cache,
    provider_name: str,
    settings,
    agg_model: str,
    run_id: str,
    capture_prompt_trace,
    prompt_events: list[dict],
    build_final_event,
):
    base = _base()
    analyze_instruction_fn = getattr(runtime_api, "_analyze_instruction", None)
    analyze_instruction_module = str(getattr(analyze_instruction_fn, "__module__", "") or "")
    analysis_override_active = callable(analyze_instruction_fn) and (
        not analyze_instruction_module.startswith("writing_agent.")
    )
    analysis_cache_key = runtime_api._runtime_json_cache_key(
        local_cache,
        "analysis_v1",
        provider_name,
        agg_model,
        instruction,
        current_text,
        list(required_outline or []),
        list(required_h2 or []),
    )
    analysis_start_ts = time.time()
    analysis_fast_mode = str(os.environ.get("WRITING_AGENT_ANALYSIS_FAST", "")).strip().lower()
    bypass_analysis_cache = analysis_fast_mode in {"force", "always"} or analysis_override_active
    analysis = None if bypass_analysis_cache else runtime_api._runtime_json_cache_get(local_cache, analysis_cache_key)
    if isinstance(analysis, dict):
        yield {"event": "analysis_cache_hit", "cache_namespace": "analysis_v1"}
        runtime_api._record_phase_timing(
            run_id,
            {"phase": "ANALYSIS", "event": "end", "duration_s": time.time() - analysis_start_ts, "cache_hit": True},
        )
    else:
        if runtime_api._should_synthesize_analysis(
            instruction=instruction,
            current_text=current_text,
            required_outline=required_outline,
            required_h2=required_h2,
        ):
            analysis = runtime_api._synthesize_analysis_from_requirements(
                instruction=instruction,
                required_outline=required_outline,
                required_h2=required_h2,
            )
            yield {
                "event": "analysis_synthesized",
                "reason": "fixed_outline_or_heading_constraints",
                "must_include": [
                    str(x).strip()
                    for x in ((analysis or {}).get("must_include") or [])
                    if str(x).strip()
                ][:20],
            }
        else:
            analysis = runtime_api._analyze_instruction(
                base_url=settings.base_url,
                model=agg_model,
                instruction=instruction,
                current_text=current_text,
                trace_hook=capture_prompt_trace,
            )
            yield from base._flush_trace(prompt_events)
        runtime_api._record_phase_timing(
            run_id,
            {"phase": "ANALYSIS", "event": "end", "duration_s": time.time() - analysis_start_ts, "cache_hit": False},
        )
        if isinstance(analysis, dict) and bool((analysis or {}).get("_schema_valid", True)):
            runtime_api._runtime_json_cache_put(
                local_cache,
                analysis_cache_key,
                analysis,
                metadata={"type": "analysis", "provider": provider_name, "model": agg_model},
            )

    analysis = dict(analysis or {})
    yield _analysis_event_payload(analysis)
    analysis_summary = runtime_api._format_analysis_summary(analysis, fallback=instruction)
    writer_requirement = runtime_api._format_writer_requirement(analysis, fallback=instruction)
    if analysis_summary:
        yield {"event": "delta", "delta": "Analysis completed with structured key points."}
    if bool(analysis.get("_needs_clarification")):
        reason = "analysis_needs_clarification"
        clarify_questions = _clarification_questions(analysis)
        yield build_final_event(
            text="",
            problems=[reason],
            status="interrupted",
            failure_reason=reason,
            quality_snapshot={
                "status": "interrupted",
                "reason": reason,
                "clarification_questions": clarify_questions,
            },
            runtime_status="interrupted",
            runtime_failure_reason=reason,
            quality_passed=False,
            quality_failure_reason=reason,
            extra_fields={"clarification_questions": clarify_questions},
        )
        return None

    paradigm_decision = runtime_api._classify_paradigm(
        instruction=instruction,
        analysis=analysis,
        user_override=str(
            analysis.get("user_paradigm_override")
            or os.environ.get("WRITING_AGENT_PARADIGM_OVERRIDE", "")
        ).strip(),
    )
    analysis["_paradigm"] = str(paradigm_decision.get("paradigm") or "")
    analysis["_paradigm_runner_up"] = str(paradigm_decision.get("runner_up") or "")
    analysis["_paradigm_confidence"] = float(paradigm_decision.get("confidence") or 0.0)
    analysis["_paradigm_margin"] = float(paradigm_decision.get("margin") or 0.0)
    yield {
        "event": "paradigm",
        "paradigm": str(paradigm_decision.get("paradigm") or ""),
        "runner_up": str(paradigm_decision.get("runner_up") or ""),
        "confidence": float(paradigm_decision.get("confidence") or 0.0),
        "margin": float(paradigm_decision.get("margin") or 0.0),
        "source": str(paradigm_decision.get("source") or "classifier"),
        "reasons": [str(x).strip() for x in (paradigm_decision.get("reasons") or []) if str(x).strip()][:8],
        "low_confidence": bool(paradigm_decision.get("low_confidence")),
    }

    probe_state = _resolve_low_confidence_probe(
        runtime_api,
        instruction=instruction,
        analysis=analysis,
        paradigm_decision=paradigm_decision,
        analysis_fast_mode=analysis_fast_mode,
        required_outline=required_outline,
        required_h2=required_h2,
        build_final_event=build_final_event,
    )
    for event in probe_state.get("events") or []:
        yield event
    terminal_event = probe_state.get("terminal_event")
    if terminal_event is not None:
        yield terminal_event
        return None
    forced_sections = [str(x).strip() for x in (probe_state.get("forced_sections") or []) if str(x).strip()]
    if forced_sections:
        analysis["_paradigm"] = str(probe_state.get("selected_paradigm") or analysis.get("_paradigm") or "")

    return {
        "analysis": analysis,
        "analysis_summary": analysis_summary,
        "writer_requirement": writer_requirement,
        "paradigm_decision": paradigm_decision,
        "forced_sections": forced_sections,
    }


__all__ = [name for name in globals() if not name.startswith("__")]
