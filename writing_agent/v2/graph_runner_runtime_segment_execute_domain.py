"""Runtime helpers for executing section segmentation."""

from __future__ import annotations

import queue
import time
from concurrent.futures import ThreadPoolExecutor


def _base():
    from writing_agent.v2 import graph_runner_runtime_segment_domain as base

    return base

def _plan_section_segments(**kwargs):
    return _base()._plan_section_segments(**kwargs)


def _generate_section_stream(**kwargs):
    return _base()._generate_section_stream(**kwargs)


def _section_body_len(text: str) -> int:
    return int(_base()._section_body_len(text))


def _section_segment_max_segments() -> int:
    return int(_base()._section_segment_max_segments())


def _assemble_section_segment_texts(parts: dict[int, str]) -> str:
    return str(_base()._assemble_section_segment_texts(parts))


def _drain_segment_trace_events(
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


def _assemble_section_segment_texts(parts: dict[int, str]) -> str:
    ordered = [str(parts[idx] or "").strip() for idx in sorted(parts) if str(parts[idx] or "").strip()]
    return "\n\n".join(ordered).strip()


def _draft_section_with_optional_segments(
    *,
    section_key: str,
    section_title: str,
    section_id: str,
    plan: PlanSection | None,
    contract,
    targets: SectionTargets,
    out_queue: queue.Queue[dict],
    text_store: TextStore | None,
    stream_kwargs: dict[str, object],
) -> tuple[str, bool]:
    segments = _plan_section_segments(
        section_key=section_key,
        section_title=section_title,
        plan=plan,
        contract=contract,
        targets=targets,
    )
    if not segments:
        text = _generate_section_stream(**stream_kwargs)
        return text, False

    out_queue.put(
        {
            "event": "section_segment_plan",
            "section": section_key,
            "section_id": section_id,
            "title": section_title,
            "segment_count": len(segments),
            "segments": [
                {
                    "segment_index": int(spec.get("segment_index") or 0),
                    "min_chars": int(spec.get("min_chars") or 0),
                    "focus_points": list(spec.get("focus_points") or []),
                    "workload_score": int(spec.get("workload_score") or 0),
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
                "event": "section_segment",
                "phase": "start",
                "section": section_key,
                "section_id": section_id,
                "title": section_title,
                "segment_index": segment_index,
                "segment_total": segment_total,
                "focus_points": focus_points,
            }
        )
        segment_kwargs = dict(stream_kwargs)
        segment_kwargs.update(
            {
                "plan_hint": str(spec.get("plan_hint") or ""),
                "min_paras": int(spec.get("min_paras") or 1),
                "min_chars": int(spec.get("min_chars") or 0),
                "max_chars": int(spec.get("max_chars") or 0),
                "min_tables": int(spec.get("min_tables") or 0),
                "min_figures": int(spec.get("min_figures") or 0),
                "out_queue": local_queue,
                "text_store": text_store,
            }
        )
        try:
            result = _generate_section_stream(**segment_kwargs)
            out_queue.put(
                {
                    "event": "section_segment",
                    "phase": "end",
                    "section": section_key,
                    "section_id": section_id,
                    "title": section_title,
                    "segment_index": segment_index,
                    "segment_total": segment_total,
                    "chars": _section_body_len(result),
                    "duration_s": time.time() - seg_start,
                }
            )
            return result
        except Exception as exc:
            out_queue.put(
                {
                    "event": "section_segment",
                    "phase": "error",
                    "section": section_key,
                    "section_id": section_id,
                    "title": section_title,
                    "segment_index": segment_index,
                    "segment_total": segment_total,
                    "error": str(exc)[:200],
                    "duration_s": time.time() - seg_start,
                }
            )
            raise
        finally:
            _drain_segment_trace_events(
                local_queue=local_queue,
                out_queue=out_queue,
                section=section_key,
                section_id=section_id,
                segment_index=segment_index,
                segment_total=segment_total,
            )

    try:
        segment_results: dict[int, str] = {}
        segment_workers = min(len(segments), _section_segment_max_segments())
        with ThreadPoolExecutor(max_workers=max(1, segment_workers)) as segment_pool:
            futures: list[tuple[dict[str, object], object]] = []
            for spec in segments:
                futures.append((spec, segment_pool.submit(_run_segment, spec)))
            for spec, future in futures:
                segment_results[int(spec.get("index") or 0)] = str(future.result() or "").strip()
        return _assemble_section_segment_texts(segment_results), True
    except Exception as exc:
        out_queue.put(
            {
                "event": "section_segment_fallback",
                "section": section_key,
                "section_id": section_id,
                "title": section_title,
                "reason": str(exc)[:200],
            }
        )
        text = _generate_section_stream(**stream_kwargs)
        return text, False







__all__ = [name for name in globals() if not name.startswith("__")]
