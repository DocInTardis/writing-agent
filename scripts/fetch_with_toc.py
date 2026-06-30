"""Enhanced paper fetcher: download PDFs, extract TOC, and extract KUs per chapter.

This addresses the limitation of abstract-only extraction by using full-text
PDFs and their table-of-contents structure.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import tarfile
import time
import urllib.request
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

logger = logging.getLogger(__name__)


def download_arxiv_pdf(arxiv_id: str, pdf_dir: Path, timeout: float = 120.0) -> Path | None:
    """Download arXiv PDF to local cache."""
    pdf_dir = Path(pdf_dir)
    pdf_dir.mkdir(parents=True, exist_ok=True)
    safe_id = arxiv_id.replace("/", "_").replace(":", "_")
    path = pdf_dir / f"{safe_id}.pdf"
    if path.exists() and path.stat().st_size > 1024:
        return path
    url = f"http://arxiv.org/pdf/{arxiv_id}.pdf"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "writing-agent/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            path.write_bytes(resp.read())
        logger.info("Downloaded PDF: %s (%d KB)", arxiv_id, path.stat().st_size // 1024)
        return path
    except Exception as exc:
        logger.warning("Failed to download PDF %s: %s", arxiv_id, exc)
        return None


def extract_toc_from_pdf(pdf_path: Path) -> list[dict[str, Any]]:
    """Extract table of contents from PDF bookmarks/outline."""
    try:
        import pypdf
    except ImportError:
        logger.warning("pypdf not installed; cannot extract TOC")
        return []

    reader = pypdf.PdfReader(str(pdf_path))
    outline = reader.outline
    if not outline:
        logger.debug("No bookmarks/outline found in %s", pdf_path.name)
        return []

    toc: list[dict[str, Any]] = []
    for item in outline:
        if isinstance(item, dict):
            title = str(item.get("/Title", "")).strip()
            page = int(item.get("/Page", 0))
        else:
            title = str(getattr(item, "title", "")).strip()
            try:
                page = reader.get_destination_page_number(item)
            except Exception:
                page = 0
        if title and not title.lower().startswith("page "):
            toc.append({"title": title, "page": page})
    return toc


def extract_text_by_chapters(pdf_path: Path, toc: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Split PDF text by TOC chapters."""
    try:
        import pypdf
    except ImportError:
        return []

    reader = pypdf.PdfReader(str(pdf_path))
    total_pages = len(reader.pages)
    chapters: list[dict[str, Any]] = []

    for i, entry in enumerate(toc):
        start_page = entry["page"]
        end_page = toc[i + 1]["page"] if i + 1 < len(toc) else total_pages
        texts: list[str] = []
        for p in range(start_page, min(end_page, total_pages)):
            try:
                page_text = reader.pages[p].extract_text() or ""
                texts.append(page_text)
            except Exception:
                continue
        body = "\n".join(texts).strip()
        if len(body) > 200:
            chapters.append({
                "title": entry["title"],
                "page": start_page + 1,
                "text": body,
            })
    return chapters


def extract_kus_from_chapters(
    chapters: list[dict[str, Any]],
    paper_id: str,
    paper_title: str,
    paper_authors: list[str],
    extractor=None,
) -> list[Any]:
    """Run KU extraction per chapter for finer granularity."""
    sys_path_inserted = False
    if str(Path(__file__).resolve().parents[1]) not in sys.path:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        sys_path_inserted = True

    from writing_agent.v2.rag.knowledge_unit import KnowledgeUnitExtractor

    ext = extractor or KnowledgeUnitExtractor()
    all_units: list[Any] = []

    for ch in chapters:
        if len(ch["text"]) < 300:
            continue
        # Use chapter title as context for better extraction
        context_text = f"Chapter: {ch['title']}\n\n{ch['text'][:4000]}"
        units = ext.extract_from_text(
            text=context_text,
            source_doc=paper_id,
            source_title=paper_title,
            source_authors=paper_authors,
            max_units=8,
        )
        # Enrich with page number from chapter
        for u in units:
            try:
                u.source_page = ch["page"]
            except Exception:
                pass
        all_units.extend(units)
        time.sleep(0.8)

    if sys_path_inserted:
        sys.path.pop(0)
    return all_units


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch papers with TOC-aware KU extraction")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--limit", type=int, default=5, help="Max papers to process")
    parser.add_argument("--output", type=str, default=".data/kg", help="Output directory")
    parser.add_argument("--pdf-dir", type=str, default=".data/kg/pdfs", help="PDF cache dir")
    parser.add_argument("--timeout", type=float, default=120.0, help="PDF download timeout")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    # Import fetchers from original script
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from fetch_academic_papers import fetch_arxiv, merge_records

    papers = fetch_arxiv(args.query, limit=args.limit)
    papers = merge_records(papers)
    logger.info("Fetched %d unique papers", len(papers))

    pdf_dir = Path(args.pdf_dir)
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from writing_agent.v2.rag.knowledge_unit import KUStore
    from writing_agent.v2.rag.knowledge_graph import KnowledgeGraph

    store = KUStore(out_dir)
    kg = KnowledgeGraph()
    total_units = 0

    for p in papers:
        if not p.pdf_url:
            logger.debug("Skipping %s: no PDF", p.paper_id)
            continue
        logger.info("Processing: %s", p.title[:60])

        pdf_path = download_arxiv_pdf(p.paper_id, pdf_dir, timeout=args.timeout)
        if not pdf_path:
            # Fallback to abstract-only
            if p.abstract and len(p.abstract) > 100:
                from writing_agent.v2.rag.knowledge_unit import KnowledgeUnitExtractor
                ext = KnowledgeUnitExtractor()
                units = ext.extract_from_text(
                    text=p.abstract,
                    source_doc=p.paper_id,
                    source_title=p.title,
                    source_authors=p.authors,
                    max_units=5,
                )
                if units:
                    added = store.save(units)
                    total_units += added
                    kg.build_from_kus(units)
            continue

        toc = extract_toc_from_pdf(pdf_path)
        if toc:
            logger.info("  TOC: %d chapters", len(toc))
            chapters = extract_text_by_chapters(pdf_path, toc)
            logger.info("  Extracted %d chapter texts", len(chapters))
            from writing_agent.v2.rag.knowledge_unit import KnowledgeUnitExtractor
            ext = KnowledgeUnitExtractor()
            units = extract_kus_from_chapters(
                chapters, p.paper_id, p.title, p.authors, extractor=ext
            )
        else:
            # No TOC: extract from first few pages as fallback
            logger.info("  No TOC found, extracting from first 3 pages")
            try:
                import pypdf
                reader = pypdf.PdfReader(str(pdf_path))
                texts = []
                for i in range(min(3, len(reader.pages))):
                    t = reader.pages[i].extract_text() or ""
                    texts.append(t)
                body = "\n".join(texts).strip()
                if len(body) > 300:
                    from writing_agent.v2.rag.knowledge_unit import KnowledgeUnitExtractor
                    ext = KnowledgeUnitExtractor()
                    units = ext.extract_from_text(
                        text=body,
                        source_doc=p.paper_id,
                        source_title=p.title,
                        source_authors=p.authors,
                        max_units=5,
                    )
                else:
                    units = []
            except Exception:
                units = []

        if units:
            added = store.save(units)
            total_units += added
            kg.build_from_kus(units)
            logger.info("  Added %d KUs", added)

    kg.save(out_dir / "knowledge_graph.json")
    logger.info("Done. Total KUs: %d | KG: %s", total_units, kg.stats())


if __name__ == "__main__":
    main()
