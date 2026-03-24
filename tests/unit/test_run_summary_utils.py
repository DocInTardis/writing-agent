from __future__ import annotations

from scripts.run_summary_utils import extract_section_originality_summary


def test_extract_section_originality_summary_normalizes_and_sorts_rows() -> None:
    snapshot = {
        "section_originality_hot_sample": {
            "enabled": True,
            "event_count": 5,
            "checked_event_count": 4,
            "passed_event_count": 2,
            "failed_event_count": 2,
            "checked_section_count": 2,
            "failed_section_count": 1,
            "failed_section_ratio": 0.5,
            "rewrite_count": 1,
            "rewrite_section_count": 1,
            "rewrite_rate_vs_failed_sections": 1.0,
            "retry_count": 0,
            "retry_section_count": 0,
            "retry_rate_vs_failed_sections": 0.0,
            "cache_rejected_count": 1,
            "fast_draft_rejected_count": 1,
            "rows": [
                {
                    "section": "sec-b",
                    "section_id": "sec_002",
                    "title": "B",
                    "phases": ["initial"],
                    "checked_event_count": 1,
                    "failed_event_count": 0,
                    "rewrite_count": 0,
                    "retry_count": 0,
                    "cache_rejected_count": 0,
                    "fast_draft_rejected_count": 0,
                    "latest_passed": True,
                    "max_repeat_sentence_ratio": 0.01,
                    "max_formulaic_opening_ratio": 0.05,
                    "max_source_overlap_ratio": 0.0,
                },
                {
                    "section": "sec-a",
                    "section_id": "sec_001",
                    "title": "A",
                    "phases": ["fast_draft", "initial", "post_rewrite"],
                    "checked_event_count": 3,
                    "failed_event_count": 2,
                    "rewrite_count": 1,
                    "retry_count": 0,
                    "cache_rejected_count": 1,
                    "fast_draft_rejected_count": 1,
                    "latest_passed": True,
                    "max_repeat_sentence_ratio": 0.12,
                    "max_formulaic_opening_ratio": 1.0,
                    "max_source_overlap_ratio": 0.0,
                },
            ],
        }
    }

    out = extract_section_originality_summary(snapshot)
    assert out["enabled"] is True
    assert out["failed_section_count"] == 1
    assert out["rewrite_count"] == 1
    assert out["fast_draft_rejected_count"] == 1
    assert len(out["rows"]) == 2
    assert out["rows"][0]["section_id"] == "sec_001"
    assert out["top_risk_sections"][0]["section_id"] == "sec_001"


def test_extract_section_originality_summary_handles_missing_payload() -> None:
    out = extract_section_originality_summary({})
    assert out["enabled"] is False
    assert out["event_count"] == 0
    assert out["rows"] == []
    assert out["top_risk_sections"] == []
