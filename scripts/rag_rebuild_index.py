"""Rag Rebuild Index command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from writing_agent.v2.rag.index import RagIndex  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Rebuild the RAG chunk index (optional embeddings).")
    ap.add_argument("--embed", action=argparse.BooleanOptionalAction, default=True, help="use Ollama embeddings when indexing")
    ap.add_argument("--data-dir", default="", help="override WRITING_AGENT_DATA_DIR (default: repo/.data)")
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    data_dir = Path(args.data_dir).resolve() if args.data_dir else Path(os.environ.get("WRITING_AGENT_DATA_DIR", str(repo_root / ".data"))).resolve()
    rag_dir = data_dir / "rag"

    index = RagIndex(rag_dir)
    total = index.rebuild(embed=bool(args.embed))
    print(f"rebuild ok chunks={total} rag_dir={str(rag_dir)!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

