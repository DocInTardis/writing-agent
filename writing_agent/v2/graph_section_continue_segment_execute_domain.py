"""Section continuation segmentation execution helpers."""

from __future__ import annotations

import queue
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

from writing_agent.v2 import graph_section_continue_segment_config_domain as config_domain
from writing_agent.v2 import graph_section_continue_segment_plan_domain as plan_domain


def _base():
    from writing_agent.v2 import graph_section_continue_segment_domain as base

    return base


def _build_continue_prompt(**kwargs):
    return _base()._build_continue_prompt(**kwargs)


def _continue_once(**kwargs):
    return _base()._continue_once(**kwargs)


def _section_body_len(text: str) -> int:
    return int(_base()._section_body_len(text))


_continue_segment_max_segments = config_domain._continue_segment_max_segments
_merge_continue_plan_hint = plan_domain._merge_continue_plan_hint
_append_incremental_text = plan_domain._append_incremental_text
_extend_continue_user_for_retry = plan_domain._extend_continue_user_for_retry
_plan_continue_segments = plan_domain._plan_continue_segments

def _drain_continue_segment_events(
    *,
    local_queue: queue.Queue[dict],
    out_queue: queue.Queue[dict],
    section: str,
    section_id: str,
    segment_index: int,
    segment_total: int,
) -> None:
    while True:
        try:
            event = local_queue.get_nowait()
        except queue.Empty:
            break
        if not isinstance(event, dict):
            continue
        if str(event.get("event") or "") == "section":
            continue
        payload = dict(event)
        payload.setdefault("section", section)
        payload.setdefault("section_id", section_id)
        payload["segment_index"] = segment_index
        payload["segment_total"] = segment_total
        out_queue.put(payload)

def _continue_with_optional_segments(
    *,
    model: str,
    title: str,
    section: str,
    parent_section: str,
    instruction: str,
    analysis_summary: str,
    evidence_summary: str,
    allowed_urls: list[str],
    plan_hint: str,
    dimension_hints: list[str] | None,
    txt: str,
    section_id: str,
    min_paras: int,
    min_chars: int,
    max_chars: int,
    min_tables: int,
    min_figures: int,
    out_queue: queue.Queue[dict],
    stream_structured_blocks: Callable[..., str],
    predict_num_tokens: Callable[[int, int, bool], int],
    is_reference_section: Callable[[str], bool],
    section_timeout_s: Callable[[], float],
    provider_factory: Callable[..., object],
    missing_chars: int,
    retry_reason: str = "",
) -> str:
    system, user = _build_continue_prompt(
        title=title,
        section=section,
        parent_section=parent_section,
        instruction=instruction,
        analysis_summary=analysis_summary,
        evidence_summary=evidence_summary,
        allowed_urls=allowed_urls,
        plan_hint=plan_hint,
        dimension_hints=dimension_hints,
        txt=txt,
        section_id=section_id,
        min_paras=min_paras,
        missing_chars=missing_chars,
        min_figures=min_figures,
    )
    body_len = _section_body_len(txt)
    user = _extend_continue_user_for_retry(
        user=user,
        txt=txt,
        body_len=body_len,
        min_chars=min_chars,
        retry_reason=retry_reason,
        missing_chars=missing_chars,
        min_figures=min_figures,
    )
    segments = _plan_continue_segments(
        section=section,
        missing_chars=missing_chars,
        min_paras=min_paras,
        min_tables=min_tables,
        min_figures=min_figures,
        dimension_hints=dimension_hints,
        is_reference_section=is_reference_section,
    )
    if not segments:
        client = provider_factory(model=model, timeout_s=240.0, route_key=f"v2.section.continue:{section}")
        return _continue_once(
            client=client,
            txt=txt,
            section=section,
            section_id=section_id,
            system=system,
            user=user,
            out_queue=out_queue,
            max_chars=max_chars,
            missing_chars=missing_chars,
            stream_structured_blocks=stream_structured_blocks,
            predict_num_tokens=predict_num_tokens,
            is_reference_section=is_reference_section,
            section_timeout_s=section_timeout_s,
        )

    out_queue.put(
        {
            "event": "section_continue_segment_plan",
            "section": section,
            "section_id": section_id,
            "segment_count": len(segments),
            "segments": [
                {
                    "segment_index": int(spec.get("segment_index") or 0),
                    "missing_chars": int(spec.get("missing_chars") or 0),
                    "focus_points": list(spec.get("focus_points") or []),
                }
                for spec in segments
            ],
        }
    )

    def _run_segment(spec: dict[str, object]) -> str:
        local_queue: queue.Queue[dict] = queue.Queue()
        segment_index = int(spec.get("segment_index") or 0)
        segment_total = int(spec.get("segment_total") or len(segments) or 0)
        focus_points = list(spec.get("focus_points") or [])
        seg_start = time.time()
        out_queue.put(
            {
                "event": "section_continue_segment",
                "phase": "start",
                "section": section,
                "section_id": section_id,
                "segment_index": segment_index,
                "segment_total": segment_total,
                "focus_points": focus_points,
            }
        )
        client = provider_factory(model=model, timeout_s=240.0, route_key=f"v2.section.continue.segment:{section}:{segment_index}")
        seg_system, seg_user = _build_continue_prompt(
            title=title,
            section=section,
            parent_section=parent_section,
            instruction=instruction,
            analysis_summary=analysis_summary,
            evidence_summary=evidence_summary,
            allowed_urls=allowed_urls,
            plan_hint=_merge_continue_plan_hint(plan_hint, dict(spec.get("plan_hint") or {})),
            dimension_hints=focus_points,
            txt=txt,
            section_id=section_id,
            min_paras=max(1, int(spec.get("min_paras") or 1)),
            missing_chars=int(spec.get("missing_chars") or 0),
        )
        seg_user = _extend_continue_user_for_retry(
            user=seg_user,
            txt=txt,
            body_len=body_len,
            min_chars=min_chars,
            retry_reason=retry_reason,
            missing_chars=int(spec.get("missing_chars") or 0),
        )
        try:
            deadline = time.time() + section_timeout_s()
            extra = stream_structured_blocks(
                client=client,
                system=seg_system,
                user=seg_user,
                out_queue=local_queue,
                section=section,
                section_id=section_id,
                is_reference=is_reference_section(section),
                num_predict=predict_num_tokens(max(120, int(spec.get("missing_chars") or 0)), max_chars, is_reference_section(section)),
                deadline=deadline,
            )
            out_queue.put(
                {
                    "event": "section_continue_segment",
                    "phase": "end",
                    "section": section,
                    "section_id": section_id,
                    "segment_index": segment_index,
                    "segment_total": segment_total,
                    "chars": _section_body_len(extra),
                    "duration_s": time.time() - seg_start,
                }
            )
            return extra
        except Exception as exc:
            out_queue.put(
                {
                    "event": "section_continue_segment",
                    "phase": "error",
                    "section": section,
                    "section_id": section_id,
                    "segment_index": segment_index,
                    "segment_total": segment_total,
                    "error": str(exc)[:200],
                    "duration_s": time.time() - seg_start,
                }
            )
            raise
        finally:
            _drain_continue_segment_events(
                local_queue=local_queue,
                out_queue=out_queue,
                section=section,
                section_id=section_id,
                segment_index=segment_index,
                segment_total=segment_total,
            )

    try:
        extras: dict[int, str] = {}
        workers = min(len(segments), _continue_segment_max_segments())
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            futures: list[tuple[dict[str, object], object]] = []
            for spec in segments:
                futures.append((spec, pool.submit(_run_segment, spec)))
            for spec, future in futures:
                extras[int(spec.get("index") or 0)] = str(future.result() or "").strip()
        combined = "\n\n".join(str(extras[idx] or "").strip() for idx in sorted(extras) if str(extras[idx] or "").strip())
        return _append_incremental_text(txt, combined)
    except Exception as exc:
        out_queue.put(
            {
                "event": "section_continue_segment_fallback",
                "section": section,
                "section_id": section_id,
                "reason": str(exc)[:200],
            }
        )
        client = provider_factory(model=model, timeout_s=240.0, route_key=f"v2.section.continue:{section}")
        return _continue_once(
            client=client,
            txt=txt,
            section=section,
            section_id=section_id,
            system=system,
            user=user,
            out_queue=out_queue,
            max_chars=max_chars,
            missing_chars=missing_chars,
            stream_structured_blocks=stream_structured_blocks,
            predict_num_tokens=predict_num_tokens,
            is_reference_section=is_reference_section,
            section_timeout_s=section_timeout_s,
        )

__all__ = [name for name in globals() if not name.startswith("__")]
