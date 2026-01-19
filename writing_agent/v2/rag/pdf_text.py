from __future__ import annotations

from pathlib import Path


def extract_pdf_text(path: Path, *, max_pages: int = 12) -> str:
    """
    Optional PDF text extraction.
    - Uses pypdf if available; otherwise returns empty string.
    - Keeps it conservative (few pages) to avoid heavy CPU/RAM use.
    """
    try:
        from pypdf import PdfReader  # type: ignore[import-not-found]
    except Exception:
        return ""

    try:
        reader = PdfReader(str(path))
    except Exception:
        return ""

    parts: list[str] = []
    for i, page in enumerate(reader.pages[: max(1, int(max_pages))]):
        try:
            txt = page.extract_text() or ""
        except Exception:
            txt = ""
        txt = (txt or "").strip()
        if txt:
            parts.append(txt)
    return "\n\n".join(parts).strip()

