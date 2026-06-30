"""Citation registration backed by structured evidence provenance."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from writing_agent.v2.rag.structured_records import CitationRecord, SourceRecord, stable_id
from writing_agent.v2.rag.structured_store import StructuredRagStore


class CitationRegistry:
    def __init__(self, rag_dir: Path) -> None:
        self.store = StructuredRagStore(rag_dir)

    def register(
        self,
        *,
        document_id: str,
        generated_section_id: str,
        claim_text: str,
        paper_id: str,
        evidence_ids: list[str],
        sentence_id: str = "",
    ) -> CitationRecord:
        evidence_map = {row.evidence_id: row for row in self.store.list_evidence(paper_id=paper_id)}
        selected = [evidence_map[eid] for eid in evidence_ids if eid in evidence_map]
        if not selected:
            raise ValueError("citation must reference evidence belonging to paper_id")
        status = "supported" if any(_supports(claim_text, row.evidence_text) for row in selected) else "needs_review"
        record = CitationRecord(
            citation_id=stable_id(
                "cit",
                document_id,
                generated_section_id,
                sentence_id,
                claim_text,
                paper_id,
                ",".join(sorted(row.evidence_id for row in selected)),
            ),
            document_id=document_id,
            generated_section_id=generated_section_id,
            sentence_id=sentence_id,
            claim_text=claim_text,
            paper_id=paper_id,
            evidence_ids=[row.evidence_id for row in selected],
            verification_status=status,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        self.store.record_citations([record])
        return record

    def references_for_document(self, document_id: str) -> list[SourceRecord]:
        sources = {row.paper_id: row for row in self.store.list_sources()}
        supported_paper_ids = {
            row.paper_id
            for row in self.store.list_citations(document_id=document_id)
            if row.verification_status == "supported"
        }
        rows = [
            sources[paper_id]
            for paper_id in sorted(supported_paper_ids)
            if paper_id in sources
        ]
        deduped: dict[str, SourceRecord] = {}
        for row in rows:
            key = str(row.doi or "").strip().lower() or re.sub(
                r"[^a-z0-9\u4e00-\u9fff]+",
                "",
                f"{row.title}{row.year or ''}".lower(),
            )
            deduped.setdefault(key or row.paper_id, row)
        return list(deduped.values())

    def register_supported_text(
        self,
        *,
        document_id: str,
        generated_section_id: str,
        text: str,
        evidence_ids: list[str],
    ) -> list[CitationRecord]:
        requested_ids = set(evidence_ids)
        available = {
            row.evidence_id: row
            for row in self.store.list_evidence()
            if row.evidence_id in requested_ids
        }
        if not available:
            return []
        citations: list[CitationRecord] = []
        sentences = [
            value.strip()
            for value in re.split(r"(?<=[。！？!?])\s*|\n+", str(text or ""))
            if len(value.strip()) >= 20
        ]
        for index, sentence in enumerate(sentences):
            ranked = sorted(
                (
                    (_support_score(sentence, evidence.evidence_text), evidence)
                    for evidence in available.values()
                ),
                key=lambda item: item[0],
                reverse=True,
            )
            if not ranked or ranked[0][0] < 0.35:
                continue
            best_score, best = ranked[0]
            selected_ids = [
                evidence.evidence_id
                for score, evidence in ranked
                if evidence.paper_id == best.paper_id and score >= max(0.35, best_score - 0.08)
            ][:3]
            citations.append(
                self.register(
                    document_id=document_id,
                    generated_section_id=generated_section_id,
                    sentence_id=f"sent_{index + 1:04d}",
                    claim_text=sentence,
                    paper_id=best.paper_id,
                    evidence_ids=selected_ids,
                )
            )
        return citations

    def references_as_dicts(self, document_id: str) -> list[dict]:
        return [
            {
                "id": row.paper_id,
                "paper_id": row.paper_id,
                "title": row.title,
                "url": row.abs_url or row.pdf_url,
                "authors": list(row.authors),
                "published": str(row.year or ""),
                "source": row.source,
                "doi": row.doi,
                "kind": "registered",
            }
            for row in self.references_for_document(document_id)
        ]

    def verify_document(self, document_id: str) -> dict[str, int]:
        citations = self.store.list_citations(document_id=document_id)
        return {
            "total": len(citations),
            "supported": sum(row.verification_status == "supported" for row in citations),
            "needs_review": sum(row.verification_status != "supported" for row in citations),
        }


def _supports(claim: str, evidence: str) -> bool:
    return (
        _support_score(claim, evidence) >= 0.35
        and _numbers_consistent(claim, evidence)
        and _negation_consistent(claim, evidence)
    )


def _support_score(claim: str, evidence: str) -> float:
    claim_tokens = _tokens(claim)
    evidence_tokens = _tokens(evidence)
    if not claim_tokens or not evidence_tokens:
        return 0.0
    overlap = len(claim_tokens & evidence_tokens)
    return overlap / max(1, len(claim_tokens))


def _tokens(text: str) -> set[str]:
    return {
        token.lower()
        for token in re.findall(
            r"[A-Za-z][A-Za-z0-9_-]{1,}|[-+]?\d+(?:\.\d+)?%?|[\u4e00-\u9fff]{2,6}",
            str(text or ""),
        )
        if token
    }


def _numbers_consistent(claim: str, evidence: str) -> bool:
    claim_numbers = set(re.findall(r"[-+]?\d+(?:\.\d+)?%?", str(claim or "")))
    if not claim_numbers:
        return True
    evidence_numbers = set(re.findall(r"[-+]?\d+(?:\.\d+)?%?", str(evidence or "")))
    return claim_numbers.issubset(evidence_numbers)


def _negation_consistent(claim: str, evidence: str) -> bool:
    pattern = re.compile(r"\b(?:not|no|never|without|cannot)\b|(?:不|未|无|没有|不能|并非)", re.IGNORECASE)
    return bool(pattern.search(str(claim or ""))) == bool(pattern.search(str(evidence or "")))
