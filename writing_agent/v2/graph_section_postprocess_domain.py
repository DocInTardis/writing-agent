"""Section draft postprocess helpers."""

from __future__ import annotations

from writing_agent.v2 import graph_section_postprocess_apply_domain as apply_domain
from writing_agent.v2 import graph_section_postprocess_format_domain as format_domain
from writing_agent.v2 import graph_section_postprocess_residue_domain as residue_domain

strip_inline_headings = format_domain.strip_inline_headings
format_references = format_domain.format_references
ensure_media_markers = format_domain.ensure_media_markers
_looks_like_prompt_residue = residue_domain._looks_like_prompt_residue
_looks_like_unsupported_claim_paragraph = residue_domain._looks_like_unsupported_claim_paragraph
_normalize_paragraph_signature = residue_domain._normalize_paragraph_signature
_near_duplicate_signature = residue_domain._near_duplicate_signature
_normalize_media_markers = format_domain._normalize_media_markers
postprocess_section = apply_domain.postprocess_section

__all__ = [name for name in globals() if not name.startswith('__')]
