"""Rag Ingest Arxiv command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from writing_agent.v2.rag.arxiv import download_arxiv_pdf, search_arxiv  # noqa: E402
from writing_agent.v2.rag.index import RagIndex  # noqa: E402
from writing_agent.v2.rag.store import RagStore  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Ingest arXiv papers into local RAG store.")
    ap.add_argument("--query", required=True, help="arXiv search query (e.g. 'retrieval augmented generation survey')")
    ap.add_argument("--max-results", type=int, default=5, help="max results per query (1-50)")
    ap.add_argument("--download-pdf", action=argparse.BooleanOptionalAction, default=True, help="download PDFs to .data/rag/papers")
    ap.add_argument("--index", action=argparse.BooleanOptionalAction, default=True, help="build/update chunk index")
    ap.add_argument("--embed", action=argparse.BooleanOptionalAction, default=True, help="use Ollama embeddings when indexing")
    ap.add_argument("--data-dir", default="", help="override WRITING_AGENT_DATA_DIR (default: repo/.data)")
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    data_dir = Path(args.data_dir).resolve() if args.data_dir else Path(os.environ.get("WRITING_AGENT_DATA_DIR", str(repo_root / ".data"))).resolve()
    rag_dir = data_dir / "rag"

    store = RagStore(rag_dir)
    index = RagIndex(rag_dir)

    existing = {p.paper_id for p in store.list_papers()}

    res = search_arxiv(query=args.query, max_results=args.max_results)
    saved = 0
    skipped = 0
    failed = 0

    for p in res.papers:
        if p.paper_id in existing:
            skipped += 1
            continue
        try:
            pdf_bytes = download_arxiv_pdf(paper_id=p.paper_id) if args.download_pdf else None
            rec = store.put_arxiv_paper(p, pdf_bytes=pdf_bytes)
            if args.index:
                try:
                    index.upsert_from_paper(rec, embed=bool(args.embed))
                except Exception:
                    pass
            saved += 1
            print(f"saved {p.paper_id}  title={p.title[:80]!r}")
        except Exception as e:
            failed += 1
            print(f"failed {p.paper_id}  err={e!r}")

    print(f"done query={args.query!r} saved={saved} skipped={skipped} failed={failed} rag_dir={str(rag_dir)!r}")
    return 0 if failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
