from __future__ import annotations

from typing import Any

from scripts.run_summary_utils import extract_section_originality_summary


DEFAULT_TARGETED_REVISION_INSTRUCTION = (
    "??????????????????????????????????????????"
    "??????????????????????????????????????????????????"
)


def pick_top_risk_sections(quality_snapshot: dict[str, Any] | None, *, limit: int = 2) -> list[str]:
    summary = extract_section_originality_summary(quality_snapshot, row_limit=max(5, int(limit or 0)))
    picked: list[str] = []
    for row in summary.get("rows") or []:
        if not isinstance(row, dict):
            continue
        title = str(row.get("title") or row.get("section") or "").strip()
        if not title:
            continue
        failed = int(row.get("failed_event_count") or 0)
        rewrites = int(row.get("rewrite_count") or 0)
        retries = int(row.get("retry_count") or 0)
        latest_passed = bool(row.get("latest_passed", True))
        if failed <= 0 and rewrites <= 0 and retries <= 0:
            continue
        if latest_passed and retries <= 0 and rewrites <= 0:
            continue
        picked.append(title)
        if len(picked) >= max(0, int(limit or 0)):
            break
    return picked


def run_targeted_section_revisions(
    *,
    client,
    doc_id: str,
    text: str,
    quality_snapshot: dict[str, Any] | None,
    max_sections: int = 2,
    instruction: str = DEFAULT_TARGETED_REVISION_INSTRUCTION,
) -> tuple[str, dict[str, Any]]:
    current_text = str(text or "")
    target_sections = pick_top_risk_sections(quality_snapshot, limit=max_sections)
    report: dict[str, Any] = {
        "attempted": 0,
        "applied": 0,
        "target_sections": list(target_sections),
        "results": [],
    }
    if not target_sections:
        report["skipped"] = True
        report["reason"] = "no_high_risk_sections"
        return current_text, report
    for title in target_sections:
        report["attempted"] = int(report.get("attempted") or 0) + 1
        payload = {
            "instruction": instruction,
            "text": current_text,
            "target_section": title,
            "allow_unscoped_fallback": False,
        }
        resp = client.post(f"/api/doc/{doc_id}/revise", json=payload)
        row: dict[str, Any] = {
            "title": title,
            "status_code": int(getattr(resp, "status_code", 0) or 0),
            "applied": False,
        }
        if int(row["status_code"]) != 200:
            row["error"] = str(getattr(resp, "text", "") or "")[:500]
            report["results"].append(row)
            continue
        data = resp.json() if getattr(resp, "content", None) else {}
        revised_text = str(data.get("text") or current_text)
        revision_meta = dict(data.get("revision_meta") or {}) if isinstance(data.get("revision_meta"), dict) else {}
        applied = bool(revised_text.strip()) and revised_text != current_text
        row["applied"] = applied
        row["revision_meta"] = revision_meta
        row["selection_source"] = str(revision_meta.get("selection_source") or "")
        row["selection_status"] = dict(revision_meta.get("selection_status") or {}) if isinstance(revision_meta.get("selection_status"), dict) else {}
        row["result_chars"] = len(revised_text)
        report["results"].append(row)
        if applied:
            current_text = revised_text
            report["applied"] = int(report.get("applied") or 0) + 1
    return current_text, report
