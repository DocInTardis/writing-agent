"""Structured records for section-aware academic retrieval."""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any


def stable_id(prefix: str, *parts: object) -> str:
    payload = "\x1f".join(str(part or "").strip() for part in parts)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20]
    return f"{prefix}_{digest}"


@dataclass(frozen=True)
class SourceRecord:
    paper_id: str
    title: str = ""
    authors: list[str] = field(default_factory=list)
    year: int | None = None
    doi: str = ""
    abstract: str = ""
    source: str = ""
    abs_url: str = ""
    pdf_url: str = ""
    fulltext_path: str = ""
    content_hash: str = ""
    processing_status: str = "discovered"
    data_level: str = "L0"
    parser_version: str = ""
    compressor_version: str = ""
    embedding_model_version: str = ""
    error_stage: str = ""
    error_message: str = ""
    retry_count: int = 0
    next_retry_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SourceRecord:
        year = data.get("year")
        try:
            normalized_year = int(year) if year not in {None, ""} else None
        except (TypeError, ValueError):
            normalized_year = None
        return cls(
            paper_id=str(data.get("paper_id") or ""),
            title=str(data.get("title") or ""),
            authors=[str(item) for item in data.get("authors") or [] if item],
            year=normalized_year,
            doi=str(data.get("doi") or ""),
            abstract=str(data.get("abstract") or ""),
            source=str(data.get("source") or ""),
            abs_url=str(data.get("abs_url") or ""),
            pdf_url=str(data.get("pdf_url") or ""),
            fulltext_path=str(data.get("fulltext_path") or ""),
            content_hash=str(data.get("content_hash") or ""),
            processing_status=str(data.get("processing_status") or "discovered"),
            data_level=str(data.get("data_level") or "L0"),
            parser_version=str(data.get("parser_version") or ""),
            compressor_version=str(data.get("compressor_version") or ""),
            embedding_model_version=str(data.get("embedding_model_version") or ""),
            error_stage=str(data.get("error_stage") or ""),
            error_message=str(data.get("error_message") or ""),
            retry_count=max(0, int(data.get("retry_count") or 0)),
            next_retry_at=str(data.get("next_retry_at") or ""),
            updated_at=str(data.get("updated_at") or ""),
        )


@dataclass(frozen=True)
class SectionRecord:
    section_id: str
    paper_id: str
    title: str
    level: int
    order: int
    parent_section_id: str = ""
    page_start: int | None = None
    page_end: int | None = None
    source_start: int | None = None
    source_end: int | None = None
    raw_text: str = ""
    summary: str = ""
    purpose: str = ""
    method: str = ""
    claims: list[str] = field(default_factory=list)
    key_facts: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    content_hash: str = ""
    parser_version: str = ""
    compressor_version: str = ""
    embedding_b64: str = ""
    embedding_dim: int = 0
    embedding_codec: str = "f32"
    embedding_scale: float = 1.0

    def retrieval_text(self) -> str:
        values = [
            self.title,
            self.summary,
            self.purpose,
            self.method,
            " ".join(self.claims),
            " ".join(self.key_facts),
            " ".join(self.limitations),
            " ".join(self.keywords),
        ]
        return "\n".join(value for value in values if value).strip()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SectionRecord:
        return cls(
            section_id=str(data.get("section_id") or ""),
            paper_id=str(data.get("paper_id") or ""),
            title=str(data.get("title") or ""),
            level=max(1, int(data.get("level") or 1)),
            order=max(0, int(data.get("order") or 0)),
            parent_section_id=str(data.get("parent_section_id") or ""),
            page_start=_optional_int(data.get("page_start")),
            page_end=_optional_int(data.get("page_end")),
            source_start=_optional_int(data.get("source_start")),
            source_end=_optional_int(data.get("source_end")),
            raw_text=str(data.get("raw_text") or ""),
            summary=str(data.get("summary") or ""),
            purpose=str(data.get("purpose") or ""),
            method=str(data.get("method") or ""),
            claims=[str(item) for item in data.get("claims") or [] if item],
            key_facts=[str(item) for item in data.get("key_facts") or [] if item],
            limitations=[str(item) for item in data.get("limitations") or [] if item],
            keywords=[str(item) for item in data.get("keywords") or [] if item],
            content_hash=str(data.get("content_hash") or ""),
            parser_version=str(data.get("parser_version") or ""),
            compressor_version=str(data.get("compressor_version") or ""),
            embedding_b64=str(data.get("embedding_b64") or ""),
            embedding_dim=max(0, int(data.get("embedding_dim") or 0)),
            embedding_codec=str(data.get("embedding_codec") or "f32"),
            embedding_scale=float(data.get("embedding_scale") or 1.0),
        )


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    paper_id: str
    section_id: str
    claim: str
    evidence_text: str
    evidence_type: str = "claim"
    page: int | None = None
    paragraph: int | None = None
    source_start: int | None = None
    source_end: int | None = None
    confidence: float = 0.5
    keywords: list[str] = field(default_factory=list)
    content_hash: str = ""
    embedding_b64: str = ""
    embedding_dim: int = 0
    embedding_codec: str = "f32"
    embedding_scale: float = 1.0

    def retrieval_text(self) -> str:
        return "\n".join(value for value in [self.claim, self.evidence_text, " ".join(self.keywords)] if value).strip()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EvidenceRecord:
        return cls(
            evidence_id=str(data.get("evidence_id") or ""),
            paper_id=str(data.get("paper_id") or ""),
            section_id=str(data.get("section_id") or ""),
            claim=str(data.get("claim") or ""),
            evidence_text=str(data.get("evidence_text") or ""),
            evidence_type=str(data.get("evidence_type") or "claim"),
            page=_optional_int(data.get("page")),
            paragraph=_optional_int(data.get("paragraph")),
            source_start=_optional_int(data.get("source_start")),
            source_end=_optional_int(data.get("source_end")),
            confidence=max(0.0, min(1.0, float(data.get("confidence") or 0.0))),
            keywords=[str(item) for item in data.get("keywords") or [] if item],
            content_hash=str(data.get("content_hash") or ""),
            embedding_b64=str(data.get("embedding_b64") or ""),
            embedding_dim=max(0, int(data.get("embedding_dim") or 0)),
            embedding_codec=str(data.get("embedding_codec") or "f32"),
            embedding_scale=float(data.get("embedding_scale") or 1.0),
        )


@dataclass(frozen=True)
class CitationRecord:
    citation_id: str
    document_id: str
    generated_section_id: str
    claim_text: str
    paper_id: str
    evidence_ids: list[str] = field(default_factory=list)
    sentence_id: str = ""
    verification_status: str = "pending"
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CitationRecord:
        return cls(
            citation_id=str(data.get("citation_id") or ""),
            document_id=str(data.get("document_id") or ""),
            generated_section_id=str(data.get("generated_section_id") or ""),
            claim_text=str(data.get("claim_text") or ""),
            paper_id=str(data.get("paper_id") or ""),
            evidence_ids=[str(item) for item in data.get("evidence_ids") or [] if item],
            sentence_id=str(data.get("sentence_id") or ""),
            verification_status=str(data.get("verification_status") or "pending"),
            created_at=str(data.get("created_at") or ""),
        )


def _optional_int(value: object) -> int | None:
    if value in {None, ""}:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
