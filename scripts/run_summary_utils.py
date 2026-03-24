from __future__ import annotations

from typing import Any


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def _as_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def extract_section_originality_summary(quality_snapshot: dict[str, Any] | None, *, row_limit: int = 10) -> dict[str, Any]:
    snapshot = quality_snapshot if isinstance(quality_snapshot, dict) else {}
    payload = snapshot.get("section_originality_hot_sample") if isinstance(snapshot.get("section_originality_hot_sample"), dict) else {}
    rows_in = payload.get("rows") if isinstance(payload.get("rows"), list) else []
    rows: list[dict[str, Any]] = []
    for row in rows_in:
        if not isinstance(row, dict):
            continue
        rows.append(
            {
                "section": str(row.get("section") or "").strip(),
                "section_id": str(row.get("section_id") or "").strip(),
                "title": str(row.get("title") or "").strip(),
                "phases": [str(x).strip() for x in (row.get("phases") or []) if str(x).strip()],
                "checked_event_count": _as_int(row.get("checked_event_count")),
                "failed_event_count": _as_int(row.get("failed_event_count")),
                "rewrite_count": _as_int(row.get("rewrite_count")),
                "retry_count": _as_int(row.get("retry_count")),
                "cache_rejected_count": _as_int(row.get("cache_rejected_count")),
                "fast_draft_rejected_count": _as_int(row.get("fast_draft_rejected_count")),
                "latest_passed": bool(row.get("latest_passed", True)),
                "max_repeat_sentence_ratio": _as_float(row.get("max_repeat_sentence_ratio")),
                "max_formulaic_opening_ratio": _as_float(row.get("max_formulaic_opening_ratio")),
                "max_source_overlap_ratio": _as_float(row.get("max_source_overlap_ratio")),
            }
        )
    rows.sort(
        key=lambda item: (
            -_as_int(item.get("failed_event_count")),
            -_as_int(item.get("rewrite_count")),
            -_as_int(item.get("retry_count")),
            -_as_float(item.get("max_formulaic_opening_ratio")),
            -_as_float(item.get("max_source_overlap_ratio")),
            str(item.get("title") or ""),
        )
    )
    limited_rows = rows[: max(0, int(row_limit or 0))] if row_limit is not None else rows
    top_risk_sections = [
        {
            "section_id": str(item.get("section_id") or ""),
            "title": str(item.get("title") or ""),
            "failed_event_count": _as_int(item.get("failed_event_count")),
            "rewrite_count": _as_int(item.get("rewrite_count")),
            "retry_count": _as_int(item.get("retry_count")),
            "latest_passed": bool(item.get("latest_passed", True)),
        }
        for item in limited_rows[:5]
    ]
    return {
        "enabled": bool(payload.get("enabled", False)),
        "event_count": _as_int(payload.get("event_count")),
        "checked_event_count": _as_int(payload.get("checked_event_count")),
        "passed_event_count": _as_int(payload.get("passed_event_count")),
        "failed_event_count": _as_int(payload.get("failed_event_count")),
        "checked_section_count": _as_int(payload.get("checked_section_count")),
        "failed_section_count": _as_int(payload.get("failed_section_count")),
        "failed_section_ratio": _as_float(payload.get("failed_section_ratio")),
        "rewrite_count": _as_int(payload.get("rewrite_count")),
        "rewrite_section_count": _as_int(payload.get("rewrite_section_count")),
        "rewrite_rate_vs_failed_sections": _as_float(payload.get("rewrite_rate_vs_failed_sections")),
        "retry_count": _as_int(payload.get("retry_count")),
        "retry_section_count": _as_int(payload.get("retry_section_count")),
        "retry_rate_vs_failed_sections": _as_float(payload.get("retry_rate_vs_failed_sections")),
        "cache_rejected_count": _as_int(payload.get("cache_rejected_count")),
        "fast_draft_rejected_count": _as_int(payload.get("fast_draft_rejected_count")),
        "rows": limited_rows,
        "top_risk_sections": top_risk_sections,
    }
