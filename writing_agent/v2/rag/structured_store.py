"""Atomic local persistence for structured RAG records."""

from __future__ import annotations

import json
import os
import re
import threading
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from writing_agent.v2.rag.structured_records import CitationRecord, EvidenceRecord, SectionRecord, SourceRecord

T = TypeVar("T")

_LOCKS: dict[str, threading.RLock] = {}
_LOCKS_GUARD = threading.Lock()


def _lock_for(path: Path) -> threading.RLock:
    key = str(path.resolve())
    with _LOCKS_GUARD:
        lock = _LOCKS.get(key)
        if lock is None:
            lock = threading.RLock()
            _LOCKS[key] = lock
        return lock


class StructuredRagStore:
    def __init__(self, rag_dir: Path) -> None:
        self.base_dir = Path(rag_dir) / "structured"
        self.sources_path = self.base_dir / "sources.jsonl"
        self.sections_path = self.base_dir / "sections.jsonl"
        self.evidence_path = self.base_dir / "evidence.jsonl"
        self.citations_path = self.base_dir / "citations.jsonl"
        self._lock = _lock_for(self.base_dir)

    def ensure(self) -> None:
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def get_source(self, paper_id: str) -> SourceRecord | None:
        pid = str(paper_id or "").strip()
        return next((row for row in self.list_sources() if row.paper_id == pid), None)

    def list_sources(self, *, status: str | None = None) -> list[SourceRecord]:
        rows = self._read(self.sources_path, SourceRecord.from_dict)
        if status is not None:
            rows = [row for row in rows if row.processing_status == status]
        return rows

    def list_canonical_sources(self, *, status: str | None = None) -> list[SourceRecord]:
        selected: dict[str, SourceRecord] = {}
        for row in self.list_sources(status=status):
            key = _source_identity(row)
            current = selected.get(key)
            if current is None or _source_rank(row) > _source_rank(current):
                selected[key] = row
        return list(selected.values())

    def list_sections(self, *, paper_id: str | None = None) -> list[SectionRecord]:
        rows = self._read(self.sections_path, SectionRecord.from_dict)
        if paper_id is not None:
            rows = [row for row in rows if row.paper_id == paper_id]
        return sorted(rows, key=lambda row: (row.paper_id, row.order, row.section_id))

    def list_evidence(
        self,
        *,
        paper_id: str | None = None,
        section_ids: set[str] | None = None,
    ) -> list[EvidenceRecord]:
        rows = self._read(self.evidence_path, EvidenceRecord.from_dict)
        if paper_id is not None:
            rows = [row for row in rows if row.paper_id == paper_id]
        if section_ids is not None:
            rows = [row for row in rows if row.section_id in section_ids]
        return rows

    def list_citations(self, *, document_id: str | None = None) -> list[CitationRecord]:
        rows = self._read(self.citations_path, CitationRecord.from_dict)
        if document_id is not None:
            rows = [row for row in rows if row.document_id == document_id]
        return rows

    def upsert_source(self, source: SourceRecord) -> None:
        if not source.paper_id:
            raise ValueError("source.paper_id is required")
        with self._lock:
            rows = self.list_sources()
            by_id = {row.paper_id: row for row in rows}
            by_id[source.paper_id] = source
            self._write(self.sources_path, [row.to_dict() for row in by_id.values()])

    def replace_document(
        self,
        *,
        source: SourceRecord,
        sections: list[SectionRecord],
        evidence: list[EvidenceRecord],
    ) -> None:
        if not source.paper_id:
            raise ValueError("source.paper_id is required")
        if any(row.paper_id != source.paper_id for row in sections):
            raise ValueError("all sections must belong to source.paper_id")
        if any(row.paper_id != source.paper_id for row in evidence):
            raise ValueError("all evidence must belong to source.paper_id")
        section_ids = {row.section_id for row in sections}
        if any(row.section_id not in section_ids for row in evidence):
            raise ValueError("evidence references an unknown section")

        with self._lock:
            sources = {row.paper_id: row for row in self.list_sources()}
            sources[source.paper_id] = source
            kept_sections = [row for row in self.list_sections() if row.paper_id != source.paper_id]
            kept_evidence = [row for row in self.list_evidence() if row.paper_id != source.paper_id]
            self._write(self.sources_path, [row.to_dict() for row in sources.values()])
            self._write(self.sections_path, [row.to_dict() for row in kept_sections + sections])
            self._write(self.evidence_path, [row.to_dict() for row in kept_evidence + evidence])

    def record_citations(self, citations: list[CitationRecord]) -> int:
        valid = [row for row in citations if row.citation_id and row.document_id and row.paper_id]
        if not valid:
            return 0
        with self._lock:
            rows = {row.citation_id: row for row in self.list_citations()}
            before = len(rows)
            for row in valid:
                rows[row.citation_id] = row
            self._write(self.citations_path, [row.to_dict() for row in rows.values()])
            return len(rows) - before

    def referenced_paper_ids(self, document_id: str) -> list[str]:
        return sorted({row.paper_id for row in self.list_citations(document_id=document_id) if row.paper_id})

    def delete_document(self, paper_id: str) -> None:
        pid = str(paper_id or "").strip()
        if not pid:
            return
        with self._lock:
            self._write(self.sources_path, [row.to_dict() for row in self.list_sources() if row.paper_id != pid])
            self._write(self.sections_path, [row.to_dict() for row in self.list_sections() if row.paper_id != pid])
            self._write(self.evidence_path, [row.to_dict() for row in self.list_evidence() if row.paper_id != pid])

    def _read(self, path: Path, factory: Callable[[dict], T]) -> list[T]:
        if not path.exists():
            return []
        out: list[T] = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            raw = line.strip()
            if not raw:
                continue
            try:
                value = json.loads(raw)
                if isinstance(value, dict):
                    out.append(factory(value))
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
        return out

    def _write(self, path: Path, rows: list[dict]) -> None:
        self.ensure()
        tmp_path = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
        payload = "\n".join(json.dumps(row, ensure_ascii=False, sort_keys=True) for row in rows)
        tmp_path.write_text(payload + ("\n" if payload else ""), encoding="utf-8")
        os.replace(tmp_path, path)


def _source_identity(source: SourceRecord) -> str:
    doi = str(source.doi or "").strip().lower()
    if doi:
        return f"doi:{doi}"
    title = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", str(source.title or "").lower())
    if title:
        return f"title:{title}:{source.year or ''}"
    return f"paper:{source.paper_id}"


def _source_rank(source: SourceRecord) -> tuple[int, int, int]:
    level = {"L2": 3, "L1": 2, "L0": 1}.get(source.data_level, 0)
    metadata = sum(bool(value) for value in (source.doi, source.abs_url, source.pdf_url, source.authors, source.year))
    return level, metadata, len(source.abstract)
