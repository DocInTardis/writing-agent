"""Knowledge Unit (KU) module — atomic claim extraction with full provenance.

Replaces coarse chunking with fine-grained, auditable knowledge atoms.
Each KU is a claim + evidence pair, traceable to source document page/paragraph.
"""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from writing_agent.llm import get_default_provider
from writing_agent.v2.rag.structured_records import EvidenceRecord

logger = logging.getLogger(__name__)


class KnowledgeUnit(BaseModel):
    """An atomic unit of knowledge extracted from a source document.

    Schema aligned with academic citation requirements:
    - claim: one-sentence core assertion
    - evidence: supporting text excerpt from source
    - source_*: precise provenance for verification
    - entities: linked concepts for graph construction
    """

    model_config = ConfigDict(validate_assignment=True)

    ku_id: str = Field(default_factory=lambda: f"KU-{uuid.uuid4().hex[:12]}")
    claim: str = Field(
        ...,
        min_length=5,
        description="Atomic claim in one sentence",
    )
    evidence: str = Field(
        ...,
        min_length=10,
        description="Verbatim excerpt supporting the claim",
    )
    source_doc: str = Field(
        ...,
        description="Source identifier (DOI / arXiv ID / URL)",
    )
    source_title: str = Field(default="")
    source_authors: list[str] = Field(default_factory=list)
    source_page: int | None = Field(default=None, ge=1)
    source_para: int | None = Field(default=None, ge=1)
    paper_id: str = Field(default="")
    section_id: str = Field(default="")
    evidence_type: str = Field(default="claim")
    source_start: int | None = Field(default=None, ge=0)
    source_end: int | None = Field(default=None, ge=0)
    content_hash: str = Field(default="")
    confidence: float = Field(default=0.85, ge=0.0, le=1.0)
    entities: list[str] = Field(
        default_factory=list,
        description="Named entities / concepts mentioned (e.g. BERT, Transformer)",
    )
    relation_hints: list[str] = Field(
        default_factory=list,
        description="Suggested relation types for graph linking",
    )

    @field_validator("claim")
    @classmethod
    def _strip_markers(cls, v: str) -> str:
        return v.strip().rstrip(".").strip() + "."

    def provenance_key(self) -> str:
        """Stable key for deduplication."""
        payload = f"{self.source_doc}|{self.claim}|{self.evidence[:80]}"
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:16]

    @classmethod
    def from_evidence_record(
        cls,
        evidence: EvidenceRecord,
        *,
        source_title: str = "",
        source_authors: list[str] | None = None,
    ) -> KnowledgeUnit:
        return cls(
            ku_id=evidence.evidence_id,
            claim=evidence.claim,
            evidence=evidence.evidence_text,
            source_doc=evidence.paper_id,
            source_title=source_title,
            source_authors=source_authors or [],
            source_page=evidence.page,
            source_para=evidence.paragraph,
            paper_id=evidence.paper_id,
            section_id=evidence.section_id,
            evidence_type=evidence.evidence_type,
            source_start=evidence.source_start,
            source_end=evidence.source_end,
            content_hash=evidence.content_hash,
            confidence=evidence.confidence,
            entities=list(evidence.keywords),
        )

    def to_evidence_record(self) -> EvidenceRecord:
        return EvidenceRecord(
            evidence_id=self.ku_id,
            paper_id=self.paper_id or self.source_doc,
            section_id=self.section_id,
            claim=self.claim,
            evidence_text=self.evidence,
            evidence_type=self.evidence_type,
            page=self.source_page,
            paragraph=self.source_para,
            source_start=self.source_start,
            source_end=self.source_end,
            confidence=self.confidence,
            keywords=list(self.entities),
            content_hash=self.content_hash,
        )

    def to_obsidian_page(self) -> str:
        """Render as Obsidian Markdown + YAML frontmatter."""
        front = {
            "ku_id": self.ku_id,
            "source_doc": self.source_doc,
            "source_title": self.source_title,
            "source_authors": self.source_authors,
            "source_page": self.source_page,
            "source_para": self.source_para,
            "confidence": self.confidence,
            "entities": self.entities,
            "relation_hints": self.relation_hints,
        }
        yaml_block = json.dumps(front, ensure_ascii=False, indent=2)
        entities_links = " ".join(f"[[{e}]]" for e in self.entities)
        return (
            f"---\n{yaml_block}\n---\n\n"
            f"## Claim\n\n{self.claim}\n\n"
            f"## Evidence\n\n> {self.evidence}\n\n"
            f"## Entities\n\n{entities_links}\n"
        )


class KUExtractionResult(BaseModel):
    """Structured LLM output for knowledge-unit extraction."""

    model_config = ConfigDict(strict=False, extra="ignore")

    units: list[KnowledgeUnit] = Field(default_factory=list)
    rejected_fragments: list[str] = Field(default_factory=list)


class KnowledgeUnitExtractor:
    """Extract KnowledgeUnits from text using LLM structured output."""

    _SYSTEM_PROMPT = (
        "<task>extract_knowledge_units</task>\n"
        "<constraints>\n"
        "You are an academic knowledge extractor. "
        "Decompose the input text into atomic claims. "
        "For each claim, provide:\n"
        "1. claim — one concise sentence stating the core finding\n"
        "2. evidence — verbatim excerpt from the text that supports it\n"
        "3. entities — key concepts/methods/datasets mentioned\n"
        "4. relation_hints — one of: supports / contradicts / extends / uses / compares\n"
        "Return strict JSON conforming to the schema.\n"
        "</constraints>"
    )

    def __init__(self) -> None:
        self._provider: Any = None

    @property
    def provider(self) -> Any:
        if self._provider is None:
            self._provider = get_default_provider()
        return self._provider

    def extract_from_text(
        self,
        text: str,
        *,
        source_doc: str,
        source_title: str = "",
        source_authors: list[str] | None = None,
        max_units: int = 20,
    ) -> list[KnowledgeUnit]:
        """Extract KUs from raw text (e.g. PDF paragraph or abstract)."""
        body = str(text or "").strip()
        if len(body) < 40:
            logger.debug("Text too short for KU extraction: %d chars", len(body))
            return []

        schema = KUExtractionResult.model_json_schema()
        user_prompt = (
            f"Extract up to {max_units} knowledge units from the text below.\n\n"
            f"Source document: {source_doc}\n"
            f"Source title: {source_title}\n\n"
            f"Text:\n---\n{body[:6000]}\n---\n\n"
            f"JSON schema:\n{json.dumps(schema, ensure_ascii=False, indent=2)}\n\n"
            "Return strict JSON only."
        )

        try:
            raw = self.provider.chat(
                system=self._SYSTEM_PROMPT,
                user=user_prompt,
                temperature=0.2,
            )
        except Exception as exc:
            logger.warning("KU extraction LLM call failed: %s", exc)
            return []

        return self._parse_response(
            raw,
            source_doc=source_doc,
            source_title=source_title,
            source_authors=source_authors or [],
        )

    def _parse_response(
        self,
        raw: str,
        *,
        source_doc: str,
        source_title: str,
        source_authors: list[str],
    ) -> list[KnowledgeUnit]:
        text = str(raw or "").strip()
        if text.startswith("```"):
            import re

            text = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", text).strip()
            text = re.sub(r"\s*```$", "", text).strip()

        # Primary: Pydantic structured parsing
        try:
            parsed = KUExtractionResult.model_validate_json(text)
            return self._enrich_units(parsed.units, source_doc, source_title, source_authors)
        except Exception:
            logger.debug("Structured KU parsing failed, trying fallback")

        # Fallback: extract JSON object
        import re

        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            try:
                parsed = KUExtractionResult.model_validate_json(m.group(0))
                return self._enrich_units(parsed.units, source_doc, source_title, source_authors)
            except Exception:
                pass

        # Last resort: heuristic line splitting for simple texts
        return self._heuristic_extract(text, source_doc, source_title, source_authors)

    @staticmethod
    def _enrich_units(
        units: list[KnowledgeUnit],
        source_doc: str,
        source_title: str,
        source_authors: list[str],
    ) -> list[KnowledgeUnit]:
        out: list[KnowledgeUnit] = []
        seen: set[str] = set()
        for u in units:
            if not u.claim or len(u.claim) < 10:
                continue
            enriched = u.model_copy(update={
                "source_doc": source_doc,
                "source_title": source_title,
                "source_authors": source_authors,
            })
            key = enriched.provenance_key()
            if key in seen:
                continue
            seen.add(key)
            out.append(enriched)
        return out

    @staticmethod
    def _heuristic_extract(
        text: str,
        source_doc: str,
        source_title: str,
        source_authors: list[str],
    ) -> list[KnowledgeUnit]:
        """Fallback for when LLM JSON parsing completely fails."""
        units: list[KnowledgeUnit] = []
        sentences = [s.strip() for s in text.replace("\n", " ").split(".") if len(s.strip()) > 20]
        for sent in sentences[:10]:
            units.append(
                KnowledgeUnit(
                    claim=sent[:200] + ".",
                    evidence=sent,
                    source_doc=source_doc,
                    source_title=source_title,
                    source_authors=source_authors,
                    confidence=0.5,
                )
            )
        return units


class KUStore:
    """Local JSONL store for KnowledgeUnits."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)
        self.ku_path = self.base_dir / "knowledge_units.jsonl"
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, units: list[KnowledgeUnit]) -> int:
        """Append units to store; dedupe by provenance_key."""
        existing = self.load()
        existing_keys = {u.provenance_key() for u in existing}
        added = 0
        with self.ku_path.open("a", encoding="utf-8") as f:
            for u in units:
                key = u.provenance_key()
                if key in existing_keys:
                    continue
                existing_keys.add(key)
                f.write(u.model_dump_json() + "\n")
                added += 1
        return added

    def load(self) -> list[KnowledgeUnit]:
        if not self.ku_path.exists():
            return []
        out: list[KnowledgeUnit] = []
        for line in self.ku_path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(KnowledgeUnit.model_validate_json(line))
            except Exception:
                continue
        return out

    def load_by_doc(self, source_doc: str) -> list[KnowledgeUnit]:
        return [u for u in self.load() if u.source_doc == source_doc]

    def load_by_entity(self, entity: str) -> list[KnowledgeUnit]:
        ent = str(entity or "").strip().lower()
        return [u for u in self.load() if any(e.lower() == ent for e in u.entities)]

    def delete_by_doc(self, source_doc: str) -> int:
        existing = self.load()
        kept = [u for u in existing if u.source_doc != source_doc]
        removed = len(existing) - len(kept)
        self._rewrite(kept)
        return removed

    def compact(self) -> int:
        """Deduplicate and rewrite store."""
        units = self.load()
        seen: dict[str, KnowledgeUnit] = {}
        for u in units:
            key = u.provenance_key()
            seen[key] = u
        compacted = list(seen.values())
        self._rewrite(compacted)
        return len(compacted)

    def _rewrite(self, units: list[KnowledgeUnit]) -> None:
        self.ku_path.write_text(
            "\n".join(u.model_dump_json() for u in units) + "\n",
            encoding="utf-8",
        )
