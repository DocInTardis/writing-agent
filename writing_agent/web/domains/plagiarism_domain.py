"""Plagiarism Domain module.

This module belongs to `writing_agent.web.domains` in the writing-agent codebase.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable


def clamp_plagiarism_threshold(value: object, default: float = 0.35) -> float:
    try:
        raw = float(value if value is not None else default)
    except Exception:
        raw = float(default)
    return max(0.05, min(0.95, raw))


def clamp_ai_rate_threshold(value: object, default: float = 0.65) -> float:
    try:
        raw = float(value if value is not None else default)
    except Exception:
        raw = float(default)
    return max(0.05, min(0.95, raw))


def normalize_plagiarism_reference_texts(raw: object) -> list[dict]:
    out: list[dict] = []
    if not isinstance(raw, list):
        return out
    for idx, item in enumerate(raw[:40]):
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        rid = str(item.get("id") or f"manual_{idx + 1}").strip()[:120] or f"manual_{idx + 1}"
        title = str(item.get("title") or rid).strip()[:200] or rid
        out.append({"id": rid, "title": title, "text": text})
    return out


def collect_plagiarism_doc_references(
    raw_doc_ids: object,
    *,
    store,
    safe_doc_text: Callable[[object], str],
    extract_title: Callable[[str], str],
    exclude_doc_id: str = "",
    max_count: int = 80,
    min_chars: int = 20,
) -> list[dict]:
    out: list[dict] = []
    if not isinstance(raw_doc_ids, list):
        return out
    seen: set[str] = set()
    cap = max(1, min(500, int(max_count or 80)))
    min_len = max(1, min(5000, int(min_chars or 20)))
    for raw in raw_doc_ids[:cap]:
        doc_id = str(raw or "").strip()
        if not doc_id:
            continue
        if exclude_doc_id and doc_id == exclude_doc_id:
            continue
        if doc_id in seen:
            continue
        seen.add(doc_id)
        session = store.get(doc_id)
        if session is None:
            continue
        text = safe_doc_text(session).strip()
        if len(text) < min_len:
            continue
        title = str(getattr(session, "title", "") or "").strip() or extract_title(text) or f"doc_{doc_id[:8]}"
        out.append({"id": doc_id, "title": title[:200], "text": text})
    return out


def dedupe_plagiarism_references(items: list[dict]) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        rid = str(item.get("id") or "").strip()
        if not rid:
            rid = f"ref_{idx + 1}"
        if rid in seen:
            suffix = 2
            candidate = f"{rid}_{suffix}"
            while candidate in seen:
                suffix += 1
                candidate = f"{rid}_{suffix}"
            rid = candidate
        seen.add(rid)
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        title = str(item.get("title") or rid).strip()[:200] or rid
        out.append({"id": rid[:120], "title": title, "text": text})
    return out


def safe_plagiarism_report_id(raw: object) -> str:
    value = str(raw or "").strip()
    if not value:
        return ""
    if not re.fullmatch(r"[A-Za-z0-9_.-]{6,80}", value):
        return ""
    return value


def new_plagiarism_report_id() -> str:
    stamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return f"{stamp}_{uuid.uuid4().hex[:8]}"


def plagiarism_report_doc_dir(doc_id: str, *, report_root: Path) -> Path:
    root = report_root / str(doc_id or "unknown").strip()
    root.mkdir(parents=True, exist_ok=True)
    return root


def build_plagiarism_report_markdown(payload: dict) -> str:
    lines: list[str] = []
    lines.append("# Plagiarism Library Scan Report")
    lines.append("")
    lines.append(f"- Doc ID: `{payload.get('doc_id')}`")
    lines.append(f"- Report ID: `{payload.get('report_id')}`")
    lines.append(f"- Created At: `{payload.get('created_at')}`")
    lines.append(f"- Threshold: `{payload.get('threshold')}`")
    lines.append(f"- Max Score: `{payload.get('max_score')}`")
    lines.append(f"- Flagged Count: `{payload.get('flagged_count')}`")
    lines.append(f"- Total References: `{payload.get('total_references')}`")
    lines.append("")
    lines.append("## Top Results")
    lines.append("")
    lines.append("| Reference | Score | Suspected | Containment | Jaccard | Winnowing | Longest Match |")
    lines.append("|---|---:|:---:|---:|---:|---:|---:|")
    for row in payload.get("results") or []:
        if not isinstance(row, dict):
            continue
        metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
        lines.append(
            "| {name} | {score:.4f} | {sus} | {contain:.4f} | {jac:.4f} | {win:.4f} | {lm} |".format(
                name=str(row.get("reference_title") or row.get("reference_id") or "").replace("|", "/")[:80],
                score=float(row.get("score") or 0.0),
                sus="Y" if bool(row.get("suspected")) else "N",
                contain=float(metrics.get("containment") or 0.0),
                jac=float(metrics.get("jaccard_resemblance") or 0.0),
                win=float(metrics.get("winnowing_overlap") or 0.0),
                lm=int(metrics.get("longest_match_chars") or 0),
            )
        )
    lines.append("")
    return "\n".join(lines).strip() + "\n"


def build_plagiarism_report_csv(payload: dict) -> str:
    import csv
    import io as _io

    output = _io.StringIO()
    writer = csv.writer(output)
    writer.writerow(
        [
            "reference_id",
            "reference_title",
            "score",
            "suspected",
            "containment",
            "jaccard_resemblance",
            "winnowing_overlap",
            "simhash_similarity",
            "sequence_ratio",
            "longest_match_chars",
            "top_evidence_snippet",
        ]
    )
    for row in payload.get("results") or []:
        if not isinstance(row, dict):
            continue
        metrics = row.get("metrics") if isinstance(row.get("metrics"), dict) else {}
        evidence = row.get("evidence") if isinstance(row.get("evidence"), list) else []
        snippet = ""
        if evidence and isinstance(evidence[0], dict):
            snippet = str(evidence[0].get("snippet") or "").replace("\r", " ").replace("\n", " ")[:200]
        writer.writerow(
            [
                str(row.get("reference_id") or ""),
                str(row.get("reference_title") or ""),
                float(row.get("score") or 0.0),
                bool(row.get("suspected")),
                float(metrics.get("containment") or 0.0),
                float(metrics.get("jaccard_resemblance") or 0.0),
                float(metrics.get("winnowing_overlap") or 0.0),
                float(metrics.get("simhash_similarity") or 0.0),
                float(metrics.get("sequence_ratio") or 0.0),
                int(metrics.get("longest_match_chars") or 0),
                snippet,
            ]
        )
    return output.getvalue()


def persist_plagiarism_report(doc_id: str, payload: dict, *, report_root: Path) -> dict:
    report_id = safe_plagiarism_report_id(payload.get("report_id")) or new_plagiarism_report_id()
    base_dir = plagiarism_report_doc_dir(doc_id, report_root=report_root)
    json_path = base_dir / f"{report_id}.json"
    md_path = base_dir / f"{report_id}.md"
    csv_path = base_dir / f"{report_id}.csv"

    normalized = dict(payload)
    normalized["report_id"] = report_id

    json_path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(build_plagiarism_report_markdown(normalized), encoding="utf-8")
    csv_path.write_text(build_plagiarism_report_csv(normalized), encoding="utf-8")
    return {
        "report_id": report_id,
        "json_path": str(json_path),
        "md_path": str(md_path),
        "csv_path": str(csv_path),
    }

