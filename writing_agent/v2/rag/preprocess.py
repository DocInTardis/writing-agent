"""Idempotent preprocessing pipeline for structured RAG data."""

from __future__ import annotations

import hashlib
import logging
import os
import re
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from writing_agent.v2.rag.pdf_text import extract_pdf_pages
from writing_agent.v2.rag.sectioning import (
    COMPRESSOR_VERSION,
    PARSER_VERSION,
    build_structured_records,
    parse_document_sections,
)
from writing_agent.v2.rag.store import RagPaperRecord, RagStore
from writing_agent.v2.rag.structured_records import SourceRecord
from writing_agent.v2.rag.structured_store import StructuredRagStore

logger = logging.getLogger(__name__)


class DocumentPreprocessor:
    def __init__(self, rag_dir: Path) -> None:
        self.rag_dir = Path(rag_dir)
        self.store = StructuredRagStore(self.rag_dir)

    def process_paper(self, paper: RagPaperRecord, *, force: bool = False, embed: bool = True) -> SourceRecord:
        source = self._source_from_paper(paper)
        existing = self.store.get_source(paper.paper_id)
        if (
            not force
            and existing is not None
            and existing.processing_status == "ready"
            and existing.content_hash == source.content_hash
            and existing.parser_version == PARSER_VERSION
            and existing.compressor_version == COMPRESSOR_VERSION
            and (not embed or bool(existing.embedding_model_version))
        ):
            return existing

        self.store.upsert_source(replace(source, processing_status="parsing", updated_at=_now()))
        try:
            pages = extract_pdf_pages(Path(paper.pdf_path), max_pages=0) if Path(paper.pdf_path).exists() else []
            full_text = "\n\n".join(page.text for page in pages).strip()
            input_text = full_text or "\n\n".join(value for value in [paper.title, paper.summary] if value).strip()
            parsed = parse_document_sections(text=input_text, pages=pages)
            sections, evidence = build_structured_records(paper_id=paper.paper_id, sections=parsed)
            sections, evidence, embedding_model = _add_embeddings(sections, evidence, enabled=embed)
            data_level = "L2" if full_text and evidence else ("L1" if sections else "L0")
            ready = replace(
                source,
                processing_status="ready",
                data_level=data_level,
                embedding_model_version=embedding_model,
                updated_at=_now(),
            )
            self.store.replace_document(source=ready, sections=sections, evidence=evidence)
            return ready
        except Exception as exc:
            retry_count = int(getattr(existing, "retry_count", 0) or 0) + 1
            failed = replace(
                source,
                processing_status="failed",
                error_stage="preprocessing",
                error_message=str(exc)[:1000],
                retry_count=retry_count,
                next_retry_at=(datetime.now(timezone.utc) + timedelta(seconds=min(3600, 30 * 2 ** min(retry_count, 6)))).isoformat(),
                updated_at=_now(),
            )
            self.store.upsert_source(failed)
            logger.warning("Structured RAG preprocessing failed for %s: %s", paper.paper_id, exc)
            return failed

    def process_text(
        self,
        *,
        paper_id: str,
        title: str,
        text: str,
        source: str = "user",
        abs_url: str = "",
        force: bool = False,
        embed: bool = True,
    ) -> SourceRecord:
        body = str(text or "").strip()
        content_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()
        record = SourceRecord(
            paper_id=paper_id,
            title=title,
            abstract="",
            source=source,
            abs_url=abs_url,
            content_hash=content_hash,
            processing_status="parsing",
            data_level="L0",
            parser_version=PARSER_VERSION,
            compressor_version=COMPRESSOR_VERSION,
            updated_at=_now(),
        )
        existing = self.store.get_source(paper_id)
        if (
            not force
            and existing is not None
            and existing.processing_status == "ready"
            and existing.content_hash == content_hash
            and existing.parser_version == PARSER_VERSION
            and existing.compressor_version == COMPRESSOR_VERSION
            and (not embed or bool(existing.embedding_model_version))
        ):
            return existing
        self.store.upsert_source(record)
        try:
            parsed = parse_document_sections(text=body)
            sections, evidence = build_structured_records(paper_id=paper_id, sections=parsed)
            sections, evidence, embedding_model = _add_embeddings(sections, evidence, enabled=embed)
            ready = replace(
                record,
                processing_status="ready",
                data_level="L2" if evidence else "L1",
                embedding_model_version=embedding_model,
                updated_at=_now(),
            )
            self.store.replace_document(source=ready, sections=sections, evidence=evidence)
            return ready
        except Exception as exc:
            retry_count = int(getattr(existing, "retry_count", 0) or 0) + 1
            failed = replace(
                record,
                processing_status="failed",
                error_stage="preprocessing",
                error_message=str(exc)[:1000],
                retry_count=retry_count,
                next_retry_at=(datetime.now(timezone.utc) + timedelta(seconds=min(3600, 30 * 2 ** min(retry_count, 6)))).isoformat(),
                updated_at=_now(),
            )
            self.store.upsert_source(failed)
            return failed

    def rebuild_all(self, *, embed: bool = True, force: bool = False) -> dict[str, int]:
        counts = {"ready": 0, "failed": 0, "skipped": 0}
        for paper in RagStore(self.rag_dir).list_papers():
            before = self.store.get_source(paper.paper_id)
            result = self.process_paper(paper, force=force, embed=embed)
            if (
                before is not None
                and before.processing_status == "ready"
                and before.content_hash == result.content_hash
                and not force
            ):
                counts["skipped"] += 1
            elif result.processing_status == "ready":
                counts["ready"] += 1
            else:
                counts["failed"] += 1
        return counts

    def retry_due(self, *, embed: bool = True, limit: int = 5) -> dict[str, int]:
        now = datetime.now(timezone.utc)
        papers = {paper.paper_id: paper for paper in RagStore(self.rag_dir).list_papers()}
        counts = {"ready": 0, "failed": 0}
        due = []
        for source in self.store.list_sources(status="failed"):
            try:
                retry_at = datetime.fromisoformat(source.next_retry_at) if source.next_retry_at else now
            except ValueError:
                retry_at = now
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            if retry_at <= now and source.paper_id in papers:
                due.append(source)
        for source in due[: max(0, int(limit))]:
            result = self.process_paper(papers[source.paper_id], force=True, embed=embed)
            counts["ready" if result.processing_status == "ready" else "failed"] += 1
        return counts

    @staticmethod
    def _source_from_paper(paper: RagPaperRecord) -> SourceRecord:
        pdf_path = Path(paper.pdf_path)
        if pdf_path.exists():
            content_hash = _hash_file(pdf_path)
        else:
            content_hash = hashlib.sha256(
                f"{paper.title}\n{paper.summary}\n{paper.updated}".encode()
            ).hexdigest()
        return SourceRecord(
            paper_id=paper.paper_id,
            title=paper.title,
            authors=list(paper.authors),
            year=_year(paper.published),
            doi=_doi(paper.abs_url),
            abstract=paper.summary,
            source=paper.source,
            abs_url=paper.abs_url,
            pdf_url=paper.pdf_url,
            fulltext_path=str(pdf_path) if pdf_path.exists() else "",
            content_hash=content_hash,
            processing_status="discovered",
            data_level="L0",
            parser_version=PARSER_VERSION,
            compressor_version=COMPRESSOR_VERSION,
            updated_at=_now(),
        )


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _year(value: str) -> int | None:
    match = re.search(r"(?:19|20)\d{2}", str(value or ""))
    return int(match.group(0)) if match else None


def _doi(value: str) -> str:
    match = re.search(r"10\.\d{4,9}/[-._;()/:A-Z0-9]+", str(value or ""), flags=re.IGNORECASE)
    return match.group(0).rstrip(".,)") if match else ""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _add_embeddings(sections, evidence, *, enabled: bool):
    if not enabled:
        return sections, evidence, ""
    try:
        from writing_agent.v2.rag.index import _embed_codec, _embed_model_name, _encode_vec, _make_embed_client

        model = _embed_model_name()
        client = _make_embed_client(model)
        if client is None:
            return sections, evidence, ""
        codec = _embed_codec()
        embedded_sections = []
        for row in sections:
            vector = client.embeddings(prompt=row.retrieval_text(), model=model)
            payload, dim, actual_codec, scale = _encode_vec(vector, codec=codec)
            embedded_sections.append(
                replace(
                    row,
                    embedding_b64=payload,
                    embedding_dim=dim,
                    embedding_codec=actual_codec,
                    embedding_scale=scale,
                )
            )
        embedded_evidence = []
        max_evidence = max(0, int(os.environ.get("WRITING_AGENT_RAG_MAX_EMBEDDED_EVIDENCE", "200") or 200))
        for index, row in enumerate(evidence):
            if index >= max_evidence:
                embedded_evidence.append(row)
                continue
            vector = client.embeddings(prompt=row.retrieval_text(), model=model)
            payload, dim, actual_codec, scale = _encode_vec(vector, codec=codec)
            embedded_evidence.append(
                replace(
                    row,
                    embedding_b64=payload,
                    embedding_dim=dim,
                    embedding_codec=actual_codec,
                    embedding_scale=scale,
                )
            )
        return embedded_sections, embedded_evidence, model
    except Exception as exc:
        logger.debug("Structured embedding skipped: %s", exc)
        return sections, evidence, ""
