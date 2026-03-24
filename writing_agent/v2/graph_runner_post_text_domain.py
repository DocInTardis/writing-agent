"""Text cleanup and section drafting helpers for graph runner post domain."""

from __future__ import annotations

from writing_agent.v2 import graph_runner_post_text_adapter_domain as adapter_domain
from writing_agent.v2 import graph_runner_post_text_sanitize_domain as sanitize_domain
from writing_agent.v2 import graph_runner_post_text_utils_domain as utils_domain

_section_body_len = utils_domain._section_body_len
_doc_body_len = utils_domain._doc_body_len
_count_text_chars = utils_domain._count_text_chars
_truncate_to_chars = utils_domain._truncate_to_chars
_blocks_to_doc_text = utils_domain._blocks_to_doc_text
_trim_total_chars = utils_domain._trim_total_chars
_sanitize_output_text = sanitize_domain._sanitize_output_text
_strip_markdown_noise = sanitize_domain._strip_markdown_noise
_should_merge_tail = sanitize_domain._should_merge_tail
_clean_generated_text = sanitize_domain._clean_generated_text
_looks_like_heading_text = sanitize_domain._looks_like_heading_text
_strip_inline_headings = adapter_domain._strip_inline_headings
_format_references = adapter_domain._format_references
_ensure_media_markers = adapter_domain._ensure_media_markers
_generic_fill_paragraph = adapter_domain._generic_fill_paragraph
_fast_fill_references = adapter_domain._fast_fill_references
_fast_fill_section = adapter_domain._fast_fill_section
_postprocess_section = adapter_domain._postprocess_section
_ensure_section_minimums_stream = adapter_domain._ensure_section_minimums_stream
_strip_reference_like_lines = adapter_domain._strip_reference_like_lines
_normalize_section_id = adapter_domain._normalize_section_id
_stream_structured_blocks = adapter_domain._stream_structured_blocks


def _normalize_final_output(text: str, *, expected_sections: list[str] | None = None) -> str:
    from writing_agent.v2.graph_runner_runtime import _normalize_final_output as _impl

    return _impl(text, expected_sections=expected_sections)


__all__ = [name for name in globals() if not name.startswith("__")]
