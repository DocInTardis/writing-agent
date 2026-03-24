"""Final document validator gate flow."""

from __future__ import annotations

import os
import re

from writing_agent.v2.figure_render import build_figure_score_manifest
from writing_agent.v2.meta_firewall import MetaFirewall
from writing_agent.v2.final_validator_metrics_domain import *
from writing_agent.v2 import final_validator_result_domain as result_domain

_META_FIREWALL = MetaFirewall()

def validate_final_document(
    *,
    title: str,
    text: str,
    sections: list[str],
    problems: list[str],
    rag_gate_dropped: list[dict] | None = None,
    figure_manifest: dict[str, object] | None = None,
    source_rows: list[dict] | None = None,
) -> dict[str, object]:
    body = str(text or "").strip()
    heading_rows = re.findall(r"(?m)^(##+)\s+(.+?)\s*$", body)
    headings = [_normalize_expected_heading(row[1]) for row in heading_rows if _normalize_expected_heading(row[1])]
    expected = [_normalize_expected_heading(x) for x in (sections or []) if _normalize_expected_heading(x)]
    section_bodies = _section_body_map(body)
    missing_sections = [sec for sec in expected if sec not in headings]
    expected_set = set(expected)
    unexpected_sections = [head for head in headings if head not in expected_set]
    expected_counts: dict[str, int] = {}
    for head in expected:
        expected_counts[head] = int(expected_counts.get(head, 0)) + 1
    seen_heading_counts: dict[str, int] = {}
    duplicate_sections: list[str] = []
    for head in headings:
        seen_heading_counts[head] = int(seen_heading_counts.get(head, 0)) + 1
        if seen_heading_counts[head] > int(expected_counts.get(head, 0)) and head not in duplicate_sections:
            duplicate_sections.append(head)
    empty_sections: list[str] = []
    for sec in expected:
        lower = str(sec or "").lower()
        if ("参考文献" in str(sec)) or ("references" in lower):
            continue
        bodies = section_bodies.get(sec) or []
        if not bodies:
            continue
        if not any(_section_body_has_content(chunk) for chunk in bodies):
            empty_sections.append(sec)
    section_order_passed = headings == expected if expected else bool(body)
    structure_passed = bool(body) and not missing_sections and not unexpected_sections and not duplicate_sections and not empty_sections and section_order_passed

    critical_prefixes = (
        "prompt_contamination",
        "reference_topic_mismatch",
        "reference_text_topic_mismatch",
        "contract_slot_violation",
        "meta_residue_detected",
        "rag_entity_mismatch",
        "rag_theme_mismatch",
    )
    semantic_passed = not any(
        any(str(problem).startswith(prefix) for prefix in critical_prefixes)
        for problem in (problems or [])
    )

    meta_scan = _META_FIREWALL.scan(body)
    meta_residue_zero = not meta_scan.has_meta
    rag_rows = [row for row in (rag_gate_dropped or []) if isinstance(row, dict)]
    entity_mismatch_rows = [row for row in rag_rows if str(row.get("reason") or "") == "rag_entity_mismatch"]
    entity_aligned = not entity_mismatch_rows
    try:
        min_title_alignment = max(
            0.0,
            min(1.0, float(os.environ.get("WRITING_AGENT_TITLE_BODY_ALIGN_MIN_SCORE", "0.18"))),
        )
    except Exception:
        min_title_alignment = 0.18
    try:
        max_repeat_ratio = max(0.0, min(1.0, float(os.environ.get("WRITING_AGENT_MAX_REPEAT_SENTENCE_RATIO", "0.05"))))
    except Exception:
        max_repeat_ratio = 0.05
    try:
        max_mirror_ratio = max(0.0, min(1.0, float(os.environ.get("WRITING_AGENT_MAX_INSTRUCTION_MIRROR_RATIO", "0.05"))))
    except Exception:
        max_mirror_ratio = 0.05
    try:
        max_template_padding_ratio = max(
            0.0,
            min(1.0, float(os.environ.get("WRITING_AGENT_MAX_TEMPLATE_PADDING_RATIO", "0.03"))),
        )
    except Exception:
        max_template_padding_ratio = 0.03
    try:
        max_low_information_ratio = max(
            0.0,
            min(1.0, float(os.environ.get("WRITING_AGENT_MAX_LOW_INFORMATION_RATIO", "0.08"))),
        )
    except Exception:
        max_low_information_ratio = 0.08

    repeat_ratio = _repeat_sentence_ratio(body)
    mirror_ratio = _instruction_mirroring_ratio(body)
    template_padding_ratio, template_padding_hits = _template_padding_ratio(body)
    low_information_ratio, low_information_hits = _low_information_ratio(body)
    placeholder_residue_ratio, placeholder_residue_hits = _placeholder_residue_ratio(body)
    information_density_ratio, information_density_hits, avg_information_density = _information_density_ratio(body)
    formulaic_opening_ratio, formulaic_opening_hits = _formulaic_opening_ratio(body)
    source_overlap_ratio, source_overlap_hits, source_overlap_sentence_count = _source_overlap_metrics(body, source_rows)
    title_body_alignment = _title_body_alignment_score(title, body)
    unsupported_claim_ratio, unsupported_claim_hits, claim_sentence_count, unsupported_numeric_claim_count = _unsupported_claim_metrics(body)
    try:
        max_placeholder_residue_ratio = max(0.0, min(1.0, float(os.environ.get("WRITING_AGENT_MAX_PLACEHOLDER_RESIDUE_RATIO", "0.0"))))
    except Exception:
        max_placeholder_residue_ratio = 0.0
    try:
        max_information_density_ratio = max(0.0, min(1.0, float(os.environ.get("WRITING_AGENT_MAX_INFORMATION_DENSITY_FAIL_RATIO", "0.25"))))
    except Exception:
        max_information_density_ratio = 0.25
    try:
        max_unsupported_claim_ratio = max(
            0.0,
            min(1.0, float(os.environ.get("WRITING_AGENT_MAX_UNSUPPORTED_CLAIM_RATIO", "0.2"))),
        )
    except Exception:
        max_unsupported_claim_ratio = 0.2
    try:
        max_unsupported_numeric_claims = max(0, int(os.environ.get("WRITING_AGENT_MAX_UNSUPPORTED_NUMERIC_CLAIMS", "0")))
    except Exception:
        max_unsupported_numeric_claims = 0
    try:
        max_formulaic_opening_ratio = max(
            0.0,
            min(1.0, float(os.environ.get("WRITING_AGENT_MAX_FORMULAIC_OPENING_RATIO", "0.22"))),
        )
    except Exception:
        max_formulaic_opening_ratio = 0.22
    try:
        max_source_overlap_ratio = max(
            0.0,
            min(1.0, float(os.environ.get("WRITING_AGENT_MAX_SOURCE_OVERLAP_RATIO", "0.12"))),
        )
    except Exception:
        max_source_overlap_ratio = 0.12
    semantic_passed = bool(
        semantic_passed
        and (repeat_ratio <= max_repeat_ratio)
        and (mirror_ratio <= max_mirror_ratio)
        and (template_padding_ratio <= max_template_padding_ratio)
        and (low_information_ratio <= max_low_information_ratio)
        and (placeholder_residue_ratio <= max_placeholder_residue_ratio)
        and (information_density_ratio <= max_information_density_ratio)
        and (formulaic_opening_ratio <= max_formulaic_opening_ratio)
        and (source_overlap_ratio <= max_source_overlap_ratio)
        and (title_body_alignment >= min_title_alignment)
        and (unsupported_claim_ratio <= max_unsupported_claim_ratio)
        and (unsupported_numeric_claim_count <= max_unsupported_numeric_claims)
    )

    reference_metrics = _reference_quality_metrics(body)
    reference_count = int(reference_metrics.get("count") or 0)
    reference_quality_passed = bool(reference_metrics.get("quality_passed", True))
    reference_sequence_passed = bool(reference_metrics.get("sequence_passed", True))
    reference_quality_issues = [str(x).strip() for x in (reference_metrics.get("issues") or []) if str(x).strip()]
    weak_reference_items = [row for row in (reference_metrics.get("weak_items") or []) if isinstance(row, dict)]
    duplicate_reference_items = [row for row in (reference_metrics.get("duplicate_items") or []) if isinstance(row, dict)]
    unformatted_reference_items = [row for row in (reference_metrics.get("unformatted_items") or []) if isinstance(row, dict)]
    weak_reference_ratio = float(reference_metrics.get("weak_ratio") or 0.0)
    max_reference_weak_ratio = float(reference_metrics.get("max_weak_ratio") or 0.0)
    weak_reference_count = int(reference_metrics.get("weak_item_count") or 0)
    duplicate_reference_count = int(reference_metrics.get("duplicate_item_count") or 0)
    unformatted_reference_count = int(reference_metrics.get("unformatted_item_count") or 0)
    expects_reference_section = any(("\u53c2\u8003\u6587\u732e" in str(sec)) or ("references" in str(sec).lower()) for sec in expected)
    try:
        enforce_reference_min = str(os.environ.get("WRITING_AGENT_ENFORCE_REFERENCE_MIN", "0")).strip().lower() in {"1", "true", "yes", "on"}
    except Exception:
        enforce_reference_min = False
    try:
        min_reference_items = max(1, int(os.environ.get("WRITING_AGENT_MIN_REFERENCE_ITEMS", "18")))
    except Exception:
        min_reference_items = 18
    reference_gate_passed = reference_quality_passed
    if enforce_reference_min and expects_reference_section:
        reference_gate_passed = bool(reference_quality_passed and reference_count >= min_reference_items)
    elif expects_reference_section and reference_count > 0:
        reference_gate_passed = reference_quality_passed
    if entity_mismatch_rows and reference_gate_passed and reference_count > 0:
        # Rejected mismatched candidates should not fail the document once enough aligned
        # references have already survived into the final output.
        entity_aligned = True

    resolved_figure_manifest = figure_manifest if isinstance(figure_manifest, dict) else build_figure_score_manifest(body)
    figure_items = [row for row in (resolved_figure_manifest.get("items") or []) if isinstance(row, dict)]
    figure_count = int(resolved_figure_manifest.get("count") or len(figure_items))
    figure_avg_score = float(resolved_figure_manifest.get("avg_score") or 0.0)
    figure_min_score = int(resolved_figure_manifest.get("min_score") or 0)
    figure_max_score = int(resolved_figure_manifest.get("max_score") or 0)
    figure_passed_count = int(resolved_figure_manifest.get("passed_count") or 0)
    figure_review_count = int(resolved_figure_manifest.get("review_count") or 0)
    figure_drop_count = int(resolved_figure_manifest.get("drop_count") or 0)
    figure_pass_ratio = float(figure_passed_count) / float(max(1, figure_count)) if figure_count > 0 else 1.0
    try:
        figure_gate_enabled = str(os.environ.get("WRITING_AGENT_FIGURE_GATE_ENABLED", "1")).strip().lower() in {"1", "true", "yes", "on"}
    except Exception:
        figure_gate_enabled = True
    try:
        min_figure_avg_score = max(0.0, min(100.0, float(os.environ.get("WRITING_AGENT_FIGURE_MIN_AVG_SCORE", "75"))))
    except Exception:
        min_figure_avg_score = 75.0
    try:
        min_figure_pass_ratio = max(0.0, min(1.0, float(os.environ.get("WRITING_AGENT_FIGURE_MIN_PASS_RATIO", "1.0"))))
    except Exception:
        min_figure_pass_ratio = 1.0
    try:
        max_figure_review_count = max(0, int(os.environ.get("WRITING_AGENT_FIGURE_MAX_REVIEW_COUNT", "0")))
    except Exception:
        max_figure_review_count = 0
    try:
        max_figure_drop_count = max(0, int(os.environ.get("WRITING_AGENT_FIGURE_MAX_DROP_COUNT", "0")))
    except Exception:
        max_figure_drop_count = 0
    figure_gate_passed = True
    if figure_gate_enabled and figure_count > 0:
        figure_gate_passed = bool(
            figure_avg_score >= min_figure_avg_score
            and figure_pass_ratio >= min_figure_pass_ratio
            and figure_review_count <= max_figure_review_count
            and figure_drop_count <= max_figure_drop_count
        )
    weak_figure_items = [
        {
            "caption": str(row.get("caption") or "").strip(),
            "score": int(row.get("score") or 0),
            "grade": str(row.get("grade") or ""),
            "recommendation": str(row.get("recommendation") or ""),
            "issues": [str(x).strip() for x in (row.get("issues") or []) if str(x).strip()],
        }
        for row in figure_items
        if str(row.get("recommendation") or "") != "keep"
    ]

    passed = bool(
        structure_passed
        and semantic_passed
        and meta_residue_zero
        and entity_aligned
        and reference_gate_passed
        and figure_gate_passed
    )
    return result_domain.build_validation_result(locals())

__all__ = [name for name in globals() if not name.startswith('__')]
