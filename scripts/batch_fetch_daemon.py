r"""Batch paper fetcher with resume support and progress tracking.

Run this and it will keep going until the target is reached.
If interrupted, re-run and it will resume from where it left off.

Usage:
    .venv\Scripts\python.exe scripts\batch_fetch_daemon.py "query" --target 100
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
import traceback
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

logger = logging.getLogger(__name__)

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.fetch_academic_papers import (  # noqa: E402
    download_arxiv_source,
    extract_toc_from_latex,
    fetch_arxiv_ids,
)
from writing_agent.v2.rag.knowledge_graph import KnowledgeGraph  # noqa: E402
from writing_agent.v2.rag.knowledge_unit import KUStore  # noqa: E402

PROGRESS_FILE = Path(".data/kg/batch_progress.json")
PROCESSED_IDS_FILE = Path(".data/kg/processed_ids.json")


def load_progress() -> dict[str, Any]:
    if PROGRESS_FILE.exists():
        try:
            return json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"total_target": 0, "completed": 0, "query": "", "errors": 0}


def save_progress(p: dict[str, Any]) -> None:
    PROGRESS_FILE.write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")


def load_processed_ids() -> set[str]:
    if PROCESSED_IDS_FILE.exists():
        try:
            return set(json.loads(PROCESSED_IDS_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
    return set()


def save_processed_ids(ids: set[str]) -> None:
    PROCESSED_IDS_FILE.write_text(json.dumps(list(ids), ensure_ascii=False, indent=2), encoding="utf-8")


def extract_kus_from_paper(
    paper: dict[str, Any],
    toc: list[dict[str, Any]],
    extractor=None,
) -> list[Any]:
    from writing_agent.v2.rag.knowledge_unit import KnowledgeUnitExtractor

    ext = extractor or KnowledgeUnitExtractor()
    context = (
        f"Paper: {paper['title']}\n"
        f"Authors: {', '.join(paper['authors'][:4])}\n"
        f"Year: {paper['year'] or 'N/A'}\n\n"
        f"Abstract:\n{paper['abstract']}\n\n"
    )
    if toc:
        toc_lines = [f"  {'  ' * (s['level'] - 1)}- {s['title']}" for s in toc]
        context += "Table of Contents:\n" + "\n".join(toc_lines) + "\n\n"
    context += (
        "Extract up to 8 knowledge units from this paper. "
        "For each unit, identify which section it most likely belongs to."
    )

    units = ext.extract_from_text(
        text=paper["abstract"],
        source_doc=paper["id"],
        source_title=paper["title"],
        source_authors=paper["authors"],
        max_units=8,
    )

    # Attach section info
    section_titles = [s["title"] for s in toc if s["level"] == 1]
    for u in units:
        claim_lower = (u.claim or "").lower()
        best_section = ""
        for sec in section_titles:
            sec_words = set(re.findall(r"[a-z]{3,}", sec.lower()))
            claim_words = set(re.findall(r"[a-z]{3,}", claim_lower))
            if sec_words & claim_words:
                best_section = sec
                break
        if best_section:
            try:
                u = u.model_copy(update={"source_para": best_section})
            except Exception:
                pass

    return units


def process_paper(
    paper: dict[str, Any],
    store: KUStore,
    kg: KnowledgeGraph,
    extractor: Any,
    processed_ids: set[str],
) -> int:
    """Process a single paper. Returns number of KUs added."""
    paper_id = paper["id"]
    if paper_id in processed_ids:
        return 0

    logger.info("Processing: %s", paper["title"][:60])

    try:
        toc: list[dict[str, Any]] = []
        src = download_arxiv_source(paper_id, timeout=15.0)
        if src:
            toc = extract_toc_from_latex(src)
            # Limit TOC to avoid huge papers slowing things down
            toc = toc[:20]
            logger.info("  TOC: %d sections", len(toc))

        units = extract_kus_from_paper(paper, toc, extractor=extractor)
        if units:
            added = store.save(units)
            kg.build_from_kus(units)
            logger.info("  Added %d KUs", added)
            processed_ids.add(paper_id)
            save_processed_ids(processed_ids)
            return added
    except Exception as exc:
        logger.warning("Failed to process %s: %s", paper_id, exc)
        traceback.print_exc()

    return 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("query", help="Search query")
    parser.add_argument("--target", type=int, default=50, help="Target number of papers")
    parser.add_argument("--batch-size", type=int, default=10, help="Papers per arXiv API call")
    parser.add_argument("--output", type=str, default=".data/kg", help="Output directory")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    store = KUStore(out_dir)
    kg = KnowledgeGraph()

    # Load existing progress
    progress = load_progress()
    processed_ids = load_processed_ids()
    completed = len(processed_ids)

    if progress.get("query") != args.query:
        # New query: reset progress if user explicitly wants, otherwise continue
        pass

    logger.info("=" * 60)
    logger.info("Batch fetch daemon started")
    logger.info("Query: %s | Target: %d | Already processed: %d", args.query, args.target, completed)
    logger.info("=" * 60)

    if completed >= args.target:
        logger.info("Target already reached (%d/%d). Exiting.", completed, args.target)
        return

    from writing_agent.v2.rag.knowledge_unit import KnowledgeUnitExtractor
    extractor = KnowledgeUnitExtractor()

    total_added = 0
    errors = 0
    offset = 0

    while completed < args.target:
        remaining = args.target - completed
        batch_limit = min(args.batch_size, remaining)

        logger.info("Fetching batch: offset=%d, limit=%d", offset, batch_limit)
        papers = fetch_arxiv_ids(args.query, limit=batch_limit)
        if not papers:
            logger.warning("No more papers found at offset %d. Stopping.", offset)
            break

        for paper in papers:
            if paper["id"] in processed_ids:
                continue
            added = process_paper(paper, store, kg, extractor, processed_ids)
            if added > 0:
                completed += 1
                total_added += added
            else:
                errors += 1
            progress["completed"] = completed
            progress["errors"] = errors
            progress["query"] = args.query
            progress["total_target"] = args.target
            save_progress(progress)
            time.sleep(0.5)  # rate limit friendly

        offset += batch_limit
        logger.info("Progress: %d/%d papers | %d KUs | %d errors", completed, args.target, total_added, errors)
        time.sleep(2.0)  # pause between batches

    kg.save(out_dir / "knowledge_graph.json")
    logger.info("=" * 60)
    logger.info("Done. Papers: %d/%d | KUs: %d | Errors: %d", completed, args.target, total_added, errors)
    logger.info("KG stats: %s", kg.stats())


if __name__ == "__main__":
    main()
