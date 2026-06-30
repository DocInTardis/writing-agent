"""Pdf Text module.

This module belongs to `writing_agent.v2.rag` in the writing-agent codebase.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PdfPageText:
    page: int
    text: str


def extract_pdf_pages(path: Path, *, max_pages: int = 0) -> list[PdfPageText]:
    """Extract page-aware PDF text when pypdf is available."""
    try:
        from pypdf import PdfReader  # type: ignore[import-not-found]
    except Exception:
        return []

    try:
        reader = PdfReader(str(path))
    except Exception:
        return []

    limit = len(reader.pages) if int(max_pages or 0) <= 0 else min(len(reader.pages), max(1, int(max_pages)))
    pages: list[PdfPageText] = []
    for index, page in enumerate(reader.pages[:limit], start=1):
        try:
            text = (page.extract_text() or "").strip()
        except Exception:
            text = ""
        if text:
            pages.append(PdfPageText(page=index, text=text))
    return pages


def extract_pdf_text(path: Path, *, max_pages: int = 12) -> str:
    """
    Optional PDF text extraction.
    - Uses pypdf if available; otherwise returns empty string.
    - Keeps it conservative (few pages) to avoid heavy CPU/RAM use.
    """
    return "\n\n".join(page.text for page in extract_pdf_pages(path, max_pages=max_pages)).strip()

