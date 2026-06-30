"""Rebuild the section-aware RAG store from existing paper metadata."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from writing_agent.v2.rag.preprocess import DocumentPreprocessor


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rag-dir", type=Path, required=True)
    parser.add_argument("--no-embed", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    result = DocumentPreprocessor(args.rag_dir).rebuild_all(
        embed=not args.no_embed,
        force=args.force,
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
