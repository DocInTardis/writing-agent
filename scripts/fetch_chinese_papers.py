"""Fetch Chinese papers from OpenAlex and extract KUs."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))
from writing_agent.v2.rag.knowledge_unit import KUStore, KnowledgeUnitExtractor
from writing_agent.v2.rag.knowledge_graph import KnowledgeGraph

QUERIES = [
    "transformer",
    "attention mechanism",
    "BERT",
    "GPT",
    "vision transformer",
    "multimodal learning",
    "self-supervised learning",
    "graph neural network",
]

OUT_DIR = Path(".data/kg")
OUT_DIR.mkdir(parents=True, exist_ok=True)


def search_openalex_zh(query: str, limit: int = 10) -> list[dict]:
    url = (
        "https://api.openalex.org/works"
        f"?filter=language:zh,default.search:{query}"
        f"&per-page={limit}"
        "&sort=relevance_score:desc"
    )
    r = httpx.get(url, timeout=30)
    r.raise_for_status()
    data = r.json()
    return data.get("results", [])


def provenance_key(paper_id: str, seq: int) -> str:
    return f"{paper_id}-abs-{seq:03d}"


def main() -> None:
    store = KUStore(OUT_DIR)
    kg = KnowledgeGraph()
    existing_kus = store.load()
    existing_keys = {u.provenance_key() for u in existing_kus}
    extractor = KnowledgeUnitExtractor()

    # Load existing graph
    graph_path = OUT_DIR / "knowledge_graph.json"
    if graph_path.exists():
        kg.load(graph_path)

    processed_ids: set[str] = set()
    total_added = 0

    for query in QUERIES:
        print(f"\nQuery: {query}")
        try:
            papers = search_openalex_zh(query, limit=5)
        except Exception as e:
            print(f"  Search failed: {e}")
            continue

        for paper in papers:
            paper_id = paper.get("id", "").replace("https://openalex.org/", "")
            if not paper_id or paper_id in processed_ids:
                continue
            processed_ids.add(paper_id)

            title = paper.get("display_name", "")
            abstract = paper.get("abstract", "") or ""
            if not abstract:
                # Try to build abstract from inverted index
                inv = paper.get("abstract_inverted_index")
                if inv:
                    words = []
                    for w, positions in inv.items():
                        for pos in positions:
                            while len(words) <= pos:
                                words.append("")
                            words[pos] = w
                    abstract = " ".join(words)

            authors = [a.get("author", {}).get("display_name", "") for a in paper.get("authorships", [])]
            source_doc = paper_id
            source_title = title

            text_to_extract = f"Title: {title}\n\nAbstract: {abstract}"
            if len(text_to_extract) < 50:
                print(f"  Skip {paper_id}: too short")
                continue

            print(f"  Processing: {title[:60]}")
            try:
                kus = extractor.extract_from_text(text_to_extract, source_doc=paper_id, source_title=title)
            except Exception as e:
                print(f"    Extract error: {e}")
                continue

            added = 0
            for idx, u in enumerate(kus):
                key = provenance_key(paper_id, idx)
                if key in existing_keys:
                    continue
                u.ku_id = key
                u.source_doc = source_doc
                u.source_title = source_title
                u.source_authors = authors
                existing_keys.add(key)
                added += 1

            if added:
                store.save(kus)
                kg.build_from_kus(kus)
                total_added += added
                print(f"    Added {added} KUs")
            else:
                print(f"    No new KUs")

            time.sleep(2.0)

        time.sleep(3.0)

    kg.save(graph_path)
    print(f"\nFINAL: {len(processed_ids)} papers | {total_added} new KUs | KG: {kg.stats()}")


if __name__ == "__main__":
    main()
