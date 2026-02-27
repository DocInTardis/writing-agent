"""Store module.

This module belongs to `writing_agent.v2.rag` in the writing-agent codebase.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from writing_agent.v2.rag.arxiv import ArxivPaper


@dataclass(frozen=True)
class RagPaperRecord:
    paper_id: str
    title: str
    summary: str
    authors: list[str]
    published: str
    updated: str
    abs_url: str
    pdf_url: str
    categories: list[str]
    primary_category: str
    pdf_path: str
    meta_path: str
    source: str = ""


class RagStore:
    def __init__(self, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)
        self.papers_dir = self.base_dir / "papers"

    def ensure(self) -> None:
        self.papers_dir.mkdir(parents=True, exist_ok=True)

    def put_arxiv_paper(self, paper: ArxivPaper, *, pdf_bytes: bytes | None) -> RagPaperRecord:
        self.ensure()
        safe = safe_paper_key(paper.paper_id)
        meta_path = self.papers_dir / f"{safe}.json"
        pdf_path = self.papers_dir / f"{safe}.pdf"

        meta = {
            "source": "arxiv",
            "paper_id": paper.paper_id,
            "title": paper.title,
            "summary": paper.summary,
            "authors": paper.authors,
            "published": paper.published,
            "updated": paper.updated,
            "abs_url": paper.abs_url,
            "pdf_url": paper.pdf_url,
            "categories": paper.categories,
            "primary_category": paper.primary_category,
            "pdf_path": str(pdf_path),
        }
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        if pdf_bytes:
            pdf_path.write_bytes(pdf_bytes)

        return RagPaperRecord(
            paper_id=paper.paper_id,
            title=paper.title,
            summary=paper.summary,
            authors=paper.authors,
            published=paper.published,
            updated=paper.updated,
            abs_url=paper.abs_url,
            pdf_url=paper.pdf_url,
            categories=paper.categories,
            primary_category=paper.primary_category,
            pdf_path=str(pdf_path),
            meta_path=str(meta_path),
            source="arxiv",
        )

    def put_openalex_work(self, work, *, pdf_bytes: bytes | None) -> RagPaperRecord:
        self.ensure()
        safe = safe_paper_key(work.paper_id)
        meta_path = self.papers_dir / f"{safe}.json"
        pdf_path = self.papers_dir / f"{safe}.pdf"

        meta = {
            "source": "openalex",
            "paper_id": work.paper_id,
            "title": work.title,
            "summary": work.summary,
            "authors": work.authors,
            "published": work.published,
            "updated": work.updated,
            "abs_url": work.abs_url,
            "pdf_url": work.pdf_url,
            "categories": work.categories,
            "primary_category": work.primary_category,
            "pdf_path": str(pdf_path),
        }
        meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        if pdf_bytes:
            pdf_path.write_bytes(pdf_bytes)

        return RagPaperRecord(
            paper_id=work.paper_id,
            title=work.title,
            summary=work.summary,
            authors=work.authors,
            published=work.published,
            updated=work.updated,
            abs_url=work.abs_url,
            pdf_url=work.pdf_url,
            categories=work.categories,
            primary_category=work.primary_category,
            pdf_path=str(pdf_path),
            meta_path=str(meta_path),
            source="openalex",
        )

    def list_papers(self) -> list[RagPaperRecord]:
        self.ensure()
        out: list[RagPaperRecord] = []
        for meta_path in sorted(self.papers_dir.glob("*.json")):
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(meta, dict):
                continue
            pid = str(meta.get("paper_id") or "")
            if not pid:
                continue
            safe = safe_paper_key(pid)
            pdf_path = self.papers_dir / f"{safe}.pdf"
            out.append(
                RagPaperRecord(
                    paper_id=pid,
                    title=str(meta.get("title") or ""),
                    summary=str(meta.get("summary") or ""),
                    authors=[str(a) for a in (meta.get("authors") or []) if a],
                    published=str(meta.get("published") or ""),
                    updated=str(meta.get("updated") or ""),
                    abs_url=str(meta.get("abs_url") or ""),
                    pdf_url=str(meta.get("pdf_url") or ""),
                    categories=[str(c) for c in (meta.get("categories") or []) if c],
                    primary_category=str(meta.get("primary_category") or ""),
                    pdf_path=str(pdf_path),
                    meta_path=str(meta_path),
                    source=str(meta.get("source") or ""),
                )
            )
        return out

    def find_pdf_path(self, paper_id: str) -> Path | None:
        pid = (paper_id or "").strip()
        if not pid:
            return None
        self.ensure()
        safe = safe_paper_key(pid)
        pdf_path = self.papers_dir / f"{safe}.pdf"
        if pdf_path.exists():
            return pdf_path
        return None


def safe_paper_key(paper_id: str) -> str:
    s = (paper_id or "").strip()
    s = s.replace("/", "_")
    s = re.sub(r"[^A-Za-z0-9._-]+", "_", s)
    s = s.strip("._-")
    return s or "paper"
