"""Build Reference Library command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from writing_agent.v2.rag.arxiv import download_arxiv_pdf, search_arxiv  # noqa: E402
from writing_agent.v2.rag.index import RagIndex  # noqa: E402
from writing_agent.v2.rag.openalex import search_openalex  # noqa: E402
from writing_agent.v2.rag.store import RagStore  # noqa: E402


DEFAULT_QUERIES = [
    "large language models survey",
    "retrieval augmented generation",
    "information retrieval",
    "natural language processing survey",
    "text generation evaluation",
    "scientific writing",
    "academic writing",
    "citation analysis",
    "knowledge graph",
    "document understanding",
    "summarization survey",
    "report generation",
    "prompt engineering",
    "text planning",
    "document summarization",
]


def _load_queries(args: argparse.Namespace) -> list[str]:
    queries: list[str] = []
    if args.query:
        for q in args.query:
            if q and q.strip():
                queries.append(q.strip())
    if args.query_file:
        path = Path(args.query_file)
        if path.exists():
            for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                queries.append(line)
    if not queries:
        queries = DEFAULT_QUERIES[:]
    # de-dup while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        key = q.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(q)
    return out


def _download_url(url: str, *, timeout_s: float = 60.0) -> bytes:
    from http.client import IncompleteRead, RemoteDisconnected
    from urllib.error import HTTPError, URLError
    from urllib.request import Request, urlopen

    if not url:
        raise ValueError("url required")
    headers = {"User-Agent": "writing-agent-studio/2.0 (+local rag builder)"}
    req = Request(url=url, headers=headers, method="GET")
    last_err: Exception | None = None
    for attempt in range(1, 4):
        try:
            with urlopen(req, timeout=timeout_s) as resp:
                return resp.read()
        except (RemoteDisconnected, IncompleteRead, URLError, HTTPError, TimeoutError) as e:
            last_err = e
            time.sleep(0.6 * attempt)
    raise last_err or RuntimeError("download failed")


def _resolve_sources(raw: str) -> list[str]:
    s = (raw or "").strip().lower()
    if not s or s == "all":
        return ["arxiv", "openalex"]
    if s in {"arxiv", "openalex"}:
        return [s]
    return ["arxiv"]


def main() -> int:
    ap = argparse.ArgumentParser(description="Build a basic local reference library (arXiv + OpenAlex).")
    ap.add_argument("--query", action="append", default=[], help="add a query (repeatable)")
    ap.add_argument("--query-file", default="", help="text file of queries (one per line)")
    ap.add_argument("--source", default="all", help="source: arxiv | openalex | all (default: all)")
    ap.add_argument("--max-results", type=int, default=12, help="max results per query (1-50)")
    ap.add_argument("--max-total", type=int, default=0, help="overall cap (0 = no cap)")
    ap.add_argument("--download-pdf", action=argparse.BooleanOptionalAction, default=False, help="download PDFs for some/all papers")
    ap.add_argument("--pdf-limit", type=int, default=0, help="per-query PDF download cap (0 = no cap)")
    ap.add_argument("--index", action=argparse.BooleanOptionalAction, default=True, help="build/update chunk index")
    ap.add_argument("--embed", action=argparse.BooleanOptionalAction, default=True, help="use Ollama embeddings when indexing")
    ap.add_argument("--sleep", type=float, default=0.8, help="sleep seconds between queries")
    ap.add_argument("--data-dir", default="", help="override WRITING_AGENT_DATA_DIR (default: repo/.data)")
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    data_dir = Path(args.data_dir).resolve() if args.data_dir else Path(os.environ.get("WRITING_AGENT_DATA_DIR", str(repo_root / ".data"))).resolve()
    rag_dir = data_dir / "rag"

    store = RagStore(rag_dir)
    index = RagIndex(rag_dir)
    existing = {p.paper_id for p in store.list_papers()}

    queries = _load_queries(args)
    max_total = max(0, int(args.max_total))
    total_saved = 0
    total_skipped = 0
    total_failed = 0
    sources = _resolve_sources(args.source)

    for q in queries:
        if max_total and total_saved >= max_total:
            break
        for source in sources:
            if max_total and total_saved >= max_total:
                break

            saved = 0
            skipped = 0
            failed = 0
            pdf_downloaded = 0

            if source == "arxiv":
                try:
                    res = search_arxiv(query=q, max_results=int(args.max_results))
                except Exception as e:
                    print(f"[query failed] source=arxiv q={q!r} err={e!r}")
                    total_failed += 1
                    continue

                for p in res.papers:
                    if max_total and total_saved >= max_total:
                        break
                    if p.paper_id in existing:
                        skipped += 1
                        total_skipped += 1
                        continue
                    pdf_bytes = None
                    if args.download_pdf:
                        if args.pdf_limit <= 0 or pdf_downloaded < int(args.pdf_limit):
                            try:
                                pdf_bytes = download_arxiv_pdf(paper_id=p.paper_id)
                                pdf_downloaded += 1
                            except Exception as e:
                                print(f"[pdf failed] {p.paper_id} err={e!r}")
                                pdf_bytes = None
                    try:
                        rec = store.put_arxiv_paper(p, pdf_bytes=pdf_bytes)
                        if args.index:
                            try:
                                index.upsert_from_paper(rec, embed=bool(args.embed))
                            except Exception:
                                pass
                        existing.add(p.paper_id)
                        saved += 1
                        total_saved += 1
                        print(f"saved {p.paper_id} title={p.title[:80]!r}")
                    except Exception as e:
                        failed += 1
                        total_failed += 1
                        print(f"failed {p.paper_id} err={e!r}")

            if source == "openalex":
                try:
                    res = search_openalex(query=q, max_results=int(args.max_results))
                except Exception as e:
                    print(f"[query failed] source=openalex q={q!r} err={e!r}")
                    total_failed += 1
                    continue

                for w in res.works:
                    if max_total and total_saved >= max_total:
                        break
                    if w.paper_id in existing:
                        skipped += 1
                        total_skipped += 1
                        continue
                    pdf_bytes = None
                    if args.download_pdf and w.pdf_url:
                        if args.pdf_limit <= 0 or pdf_downloaded < int(args.pdf_limit):
                            try:
                                pdf_bytes = _download_url(w.pdf_url)
                                pdf_downloaded += 1
                            except Exception as e:
                                print(f"[pdf failed] {w.paper_id} err={e!r}")
                                pdf_bytes = None
                    try:
                        rec = store.put_openalex_work(w, pdf_bytes=pdf_bytes)
                        if args.index:
                            try:
                                index.upsert_from_paper(rec, embed=bool(args.embed))
                            except Exception:
                                pass
                        existing.add(w.paper_id)
                        saved += 1
                        total_saved += 1
                        print(f"saved {w.paper_id} title={w.title[:80]!r}")
                    except Exception as e:
                        failed += 1
                        total_failed += 1
                        print(f"failed {w.paper_id} err={e!r}")

            print(f"[query done] source={source} q={q!r} saved={saved} skipped={skipped} failed={failed}")

        if args.sleep and args.sleep > 0:
            time.sleep(float(args.sleep))

    print(
        "done total_saved={0} total_skipped={1} total_failed={2} rag_dir={3!r}".format(
            total_saved, total_skipped, total_failed, str(rag_dir)
        )
    )
    return 0 if total_failed == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
