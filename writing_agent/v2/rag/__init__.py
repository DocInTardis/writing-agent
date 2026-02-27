"""Init module.

This module belongs to `writing_agent.v2.rag` in the writing-agent codebase.
"""

from __future__ import annotations

from .arxiv import ArxivPaper, ArxivSearchResult, search_arxiv
from .index import RagChunk, RagChunkHit, RagIndex
from .retrieve import RetrieveResult, retrieve_context
from .store import RagPaperRecord, RagStore

__all__ = [
    "ArxivPaper",
    "ArxivSearchResult",
    "RagChunk",
    "RagChunkHit",
    "RagIndex",
    "RagPaperRecord",
    "RagStore",
    "RetrieveResult",
    "retrieve_context",
    "search_arxiv",
]
