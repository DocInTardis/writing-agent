"""Multi-query batch fetcher with retry logic.

Uses multiple related queries to avoid deep pagination on a single query.
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

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from writing_agent.v2.rag.knowledge_unit import KUStore, KnowledgeUnitExtractor
from writing_agent.v2.rag.knowledge_graph import KnowledgeGraph
from scripts.fetch_academic_papers import download_arxiv_source, extract_toc_from_latex, fetch_arxiv_ids


PROCESSED_IDS_FILE = Path(".data/kg/processed_ids.json")

def load_processed_ids() -> set[str]:
    if PROCESSED_IDS_FILE.exists():
        try:
            return set(json.loads(PROCESSED_IDS_FILE.read_text(encoding="utf-8")))
        except Exception:
            pass
    return set()

def save_processed_ids(ids: set[str]) -> None:
    PROCESSED_IDS_FILE.write_text(json.dumps(list(ids), ensure_ascii=False, indent=2), encoding="utf-8")


def extract_kus(paper: dict[str, Any], toc: list[dict[str, Any]], extractor: Any) -> list[Any]:
    units = extractor.extract_from_text(
        text=paper["abstract"],
        source_doc=paper["id"],
        source_title=paper["title"],
        source_authors=paper["authors"],
        max_units=8,
    )
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


def process_paper(paper: dict[str, Any], store: KUStore, kg: KnowledgeGraph, extractor: Any, processed_ids: set[str]) -> int:
    pid = paper["id"]
    if pid in processed_ids:
        return 0
    logger.info("Processing: %s", paper["title"][:60])
    try:
        toc = []
        src = download_arxiv_source(pid, timeout=15.0)
        if src:
            toc = extract_toc_from_latex(src)[:20]
            logger.info("  TOC: %d sections", len(toc))
        units = extract_kus(paper, toc, extractor)
        if units:
            added = store.save(units)
            kg.build_from_kus(units)
            logger.info("  Added %d KUs", added)
            processed_ids.add(pid)
            save_processed_ids(processed_ids)
            return added
    except Exception as exc:
        logger.warning("Failed %s: %s", pid, exc)
    return 0


def fetch_with_retry(query: str, limit: int, max_retries: int = 3) -> list[dict[str, Any]]:
    for attempt in range(max_retries):
        papers = fetch_arxiv_ids(query, limit=limit)
        if papers:
            return papers
        logger.info("Retry %d/%d for query: %s", attempt + 1, max_retries, query)
        time.sleep(5 * (attempt + 1))
    return []


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-per-query", type=int, default=15, help="Papers per query")
    parser.add_argument("--output", type=str, default=".data/kg")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    queries = [
        "transformer architecture",
        "attention mechanism",
        "BERT pretraining",
        "GPT language model",
        "vision transformer",
        "multimodal learning",
        "self-supervised learning",
        "graph neural network",
    ]

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)
    store = KUStore(out_dir)
    kg = KnowledgeGraph()
    processed_ids = load_processed_ids()
    extractor = KnowledgeUnitExtractor()

    total_added = 0

    for query in queries:
        logger.info("=" * 50)
        logger.info("Query: %s", query)
        papers = fetch_with_retry(query, limit=args.target_per_query)
        if not papers:
            logger.warning("Skipping query: %s", query)
            continue
        for paper in papers:
            added = process_paper(paper, store, kg, extractor, processed_ids)
            total_added += added
            time.sleep(0.5)
        logger.info("Progress: %d papers processed | %d KUs total", len(processed_ids), total_added)
        time.sleep(3)

    kg.save(out_dir / "knowledge_graph.json")
    logger.info("=" * 50)
    logger.info("FINAL: %d papers | %d KUs | KG: %s", len(processed_ids), total_added, kg.stats())


if __name__ == "__main__":
    main()
