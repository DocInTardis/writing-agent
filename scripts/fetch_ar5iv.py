"""Fetch papers via ar5iv HTML (no PDF download needed).

ar5iv converts arXiv LaTeX to semantic HTML with clean <section> tags.
Much faster and more reliable than PDF parsing, especially in regions
with slow arXiv PDF access.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# arXiv search (same as before)
# --------------------------------------------------------------------------- #

def fetch_arxiv_ids(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Search arXiv and return list of {id, title, authors, year, abstract}."""
    import xml.etree.ElementTree as ET

    url = (
        "http://export.arxiv.org/api/query?"
        f"search_query=all:{query.replace(' ', '+')}&"
        f"start=0&max_results={limit}&"
        "sortBy=relevance&sortOrder=descending"
    )
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "writing-agent/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            xml_text = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        logger.warning("arXiv search failed: %s", exc)
        return []

    ns = {"atom": "http://www.w3.org/2005/Atom"}
    results: list[dict[str, Any]] = []
    try:
        root = ET.fromstring(xml_text)
        for entry in root.findall("atom:entry", ns):
            title = entry.findtext("atom:title", "", ns).replace("\n", " ").strip()
            summary = entry.findtext("atom:summary", "", ns).strip()
            id_url = entry.findtext("atom:id", "", ns)
            paper_id = id_url.split("/abs/")[-1] if "/abs/" in id_url else id_url
            authors = [a.findtext("atom:name", "", ns) for a in entry.findall("atom:author", ns)]
            year = None
            published = entry.findtext("atom:published", "", ns)
            if published:
                m = re.search(r"(\d{4})", published)
                if m:
                    year = int(m.group(1))
            results.append({
                "id": paper_id,
                "title": title,
                "authors": authors,
                "year": year,
                "abstract": summary,
            })
    except Exception as exc:
        logger.warning("arXiv parse failed: %s", exc)
    return results


# --------------------------------------------------------------------------- #
# ar5iv HTML fetch + parse
# --------------------------------------------------------------------------- #

def fetch_ar5iv_html(arxiv_id: str, timeout: float = 60.0) -> str:
    """Fetch ar5iv HTML version of an arXiv paper."""
    url = f"https://ar5iv.org/html/{arxiv_id}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "writing-agent/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        logger.warning("ar5iv fetch failed for %s: %s", arxiv_id, exc)
        return ""


def parse_sections(html: str) -> list[dict[str, Any]]:
    """Parse ar5iv HTML into sections with title and text."""
    # ar5iv uses <section> tags with aria-labelledby pointing to h2/h3
    # Strategy: split by <h2> tags, each section = h2 title + following text until next h2
    sections: list[dict[str, Any]] = []

    # Remove script/style/nav/footer/header tags
    html = re.sub(r"<script[^>]*>[\s\S]*?</script>", "", html, flags=re.I)
    html = re.sub(r"<style[^>]*>[\s\S]*?</style>", "", html, flags=re.I)
    html = re.sub(r"<nav[^>]*>[\s\S]*?</nav>", "", html, flags=re.I)
    html = re.sub(r"<footer[^>]*>[\s\S]*?</footer>", "", html, flags=re.I)
    html = re.sub(r"<header[^>]*>[\s\S]*?</header>", "", html, flags=re.I)

    # Split by <h2> boundaries
    parts = re.split(r"(<h2[^>]*>[\s\S]*?</h2>)", html, flags=re.I)
    current_title = "Abstract"
    current_texts: list[str] = []

    for part in parts:
        if re.match(r"<h2", part, re.I):
            # Save previous section
            body = " ".join(current_texts).strip()
            if len(body) > 150 and not current_title.lower().startswith("references"):
                sections.append({"title": current_title, "text": body})
            # Start new section
            current_title = re.sub(r"<[^>]+>", "", part).strip()
            current_title = re.sub(r"\s+", " ", current_title)
            current_texts = []
        else:
            text = re.sub(r"<[^>]+>", " ", part)
            text = re.sub(r"\s+", " ", text).strip()
            if text:
                current_texts.append(text)

    # Flush last section
    body = " ".join(current_texts).strip()
    if len(body) > 150 and not current_title.lower().startswith("references"):
        sections.append({"title": current_title, "text": body})

    return sections


# --------------------------------------------------------------------------- #
# KU extraction
# --------------------------------------------------------------------------- #

def extract_kus_from_sections(
    sections: list[dict[str, Any]],
    paper: dict[str, Any],
) -> list[Any]:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from writing_agent.v2.rag.knowledge_unit import KnowledgeUnitExtractor, KUStore

    ext = KnowledgeUnitExtractor()
    all_units: list[Any] = []

    for sec in sections:
        text = sec["text"]
        if len(text) < 300:
            continue
        # Truncate very long sections to avoid token limits
        text = text[:5000]
        # Prepend section title as context
        context = f"Section: {sec['title']}\n\n{text}"
        units = ext.extract_from_text(
            text=context,
            source_doc=paper["id"],
            source_title=paper["title"],
            source_authors=paper["authors"],
            max_units=6,
        )
        # Attach section info
        for u in units:
            # Store section title in source_para as a workaround for provenance
            try:
                if hasattr(u, "source_para"):
                    u.source_para = sec["title"]
            except Exception:
                pass
        all_units.extend(units)
        time.sleep(0.6)

    return all_units


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch papers via ar5iv HTML with TOC-aware extraction")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--limit", type=int, default=5, help="Max papers")
    parser.add_argument("--output", type=str, default=".data/kg", help="Output directory")
    parser.add_argument("--timeout", type=float, default=60.0, help="HTTP timeout")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    papers = fetch_arxiv_ids(args.query, limit=args.limit)
    logger.info("Found %d papers on arXiv", len(papers))

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from writing_agent.v2.rag.knowledge_unit import KUStore
    from writing_agent.v2.rag.knowledge_graph import KnowledgeGraph

    store = KUStore(out_dir)
    kg = KnowledgeGraph()
    total_units = 0

    for p in papers:
        logger.info("Processing: %s", p["title"][:60])
        html = fetch_ar5iv_html(p["id"], timeout=args.timeout)
        if not html:
            # Fallback to abstract
            if p["abstract"] and len(p["abstract"]) > 100:
                from writing_agent.v2.rag.knowledge_unit import KnowledgeUnitExtractor
                ext = KnowledgeUnitExtractor()
                units = ext.extract_from_text(
                    text=p["abstract"],
                    source_doc=p["id"],
                    source_title=p["title"],
                    source_authors=p["authors"],
                    max_units=5,
                )
                if units:
                    added = store.save(units)
                    total_units += added
                    kg.build_from_kus(units)
            continue

        sections = parse_sections(html)
        logger.info("  Parsed %d sections", len(sections))
        for sec in sections:
            logger.debug("    - %s (%d chars)", sec["title"], len(sec["text"]))

        if not sections:
            continue

        units = extract_kus_from_sections(sections, p)
        if units:
            added = store.save(units)
            total_units += added
            kg.build_from_kus(units)
            logger.info("  Added %d KUs", added)

    kg.save(out_dir / "knowledge_graph.json")
    logger.info("Done. Total KUs: %d | KG: %s", total_units, kg.stats())


if __name__ == "__main__":
    main()
