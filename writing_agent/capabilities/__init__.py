"""Business capability layer for workflow assembly."""

from .contracts import GenerateWorkflowDeps, GenerateWorkflowRequest, GraphHandler, GraphStatePatch
from .diagramming import build_diagram_spec_from_prompt, normalize_diagram_kind, normalize_diagram_spec_payload
from .editing import trim_inline_context
from .fallback_generation import build_fallback_prompt, single_pass_generate, single_pass_generate_stream
from .generation_policy import should_use_fast_generate, summarize_analysis, system_pressure_high
from .generation_quality import check_generation_quality, looks_like_prompt_echo
from .mcp_retrieval import ensure_mcp_citations, mcp_rag_retrieve, mcp_rag_search, mcp_rag_search_chunks

__all__ = [
    "build_diagram_spec_from_prompt",
    "build_fallback_prompt",
    "check_generation_quality",
    "ensure_mcp_citations",
    "GenerateWorkflowDeps",
    "GenerateWorkflowRequest",
    "GraphHandler",
    "GraphStatePatch",
    "looks_like_prompt_echo",
    "should_use_fast_generate",
    "mcp_rag_retrieve",
    "mcp_rag_search",
    "mcp_rag_search_chunks",
    "normalize_diagram_kind",
    "normalize_diagram_spec_payload",
    "single_pass_generate",
    "single_pass_generate_stream",
    "summarize_analysis",
    "system_pressure_high",
    "trim_inline_context",
]
