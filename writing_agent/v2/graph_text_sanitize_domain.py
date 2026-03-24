"""Graph Text Sanitize Domain module.

This module belongs to `writing_agent.v2` in the writing-agent codebase.
"""

from __future__ import annotations

from writing_agent.v2 import graph_text_sanitize_core_domain as core_domain
from writing_agent.v2 import graph_text_sanitize_output_domain as output_domain
from writing_agent.v2 import graph_text_sanitize_process_domain as process_domain

strip_chatty_closings = core_domain.strip_chatty_closings
compact_list_spacing = core_domain.compact_list_spacing
strip_markdown_noise = core_domain.strip_markdown_noise
_looks_like_process_line = process_domain._looks_like_process_line
_is_dedup_candidate_line = process_domain._is_dedup_candidate_line
_normalize_sentence_key = process_domain._normalize_sentence_key
_dedupe_repeated_sentences = process_domain._dedupe_repeated_sentences
_normalize_global_media_markers = process_domain._normalize_global_media_markers
normalize_punctuation = core_domain.normalize_punctuation
is_short_tail = core_domain.is_short_tail
should_merge_tail = core_domain.should_merge_tail
clean_generated_text = core_domain.clean_generated_text
sanitize_output_text = output_domain.sanitize_output_text

__all__ = [name for name in globals() if not name.startswith("__")]
