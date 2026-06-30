"""Pydantic structured output models for LLM-driven document editing.

Replaces manual JSON regex extraction with type-safe BaseModel validation.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class InlineRewriteOutput(BaseModel):
    """Structured output for inline AI rewrite operations.

    Expected JSON schema:
    {
      "output_text": "rewritten text content",
      "confidence": 0.92,
      "intent": "improve",
      "preserved_keywords": ["term1", "term2"],
      "change_summary": "short description of what changed"
    }
    """

    model_config = ConfigDict(strict=False, extra="ignore")

    output_text: str = Field(
        ...,
        description="The rewritten or generated text content",
        min_length=1,
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Model confidence in the rewrite",
    )
    intent: Literal[
        "continue",
        "improve",
        "summarize",
        "expand",
        "change_tone",
        "simplify",
        "elaborate",
        "rephrase",
        "ask_ai",
        "explain",
        "translate",
        "unknown",
    ] = Field(default="unknown")
    preserved_keywords: list[str] = Field(default_factory=list)
    change_summary: str = Field(default="")

    @field_validator("output_text")
    @classmethod
    def _strip_fences(cls, v: str) -> str:
        s = v.strip()
        if s.startswith("```"):
            import re

            s = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", s).strip()
            s = re.sub(r"\s*```$", "", s).strip()
        return s


class DocumentEditOutput(BaseModel):
    """Structured output for document-level edit operations.

    Expected JSON schema:
    {
      "html": "<full document html>",
      "assistant": "short note about applied changes",
      "meta": {
        "scope": "selection|document",
        "preserved_structure": true,
        "affected_sections": ["Introduction", "Methodology"],
        "risk_flags": []
      }
    }
    """

    model_config = ConfigDict(strict=False, extra="ignore")

    html: str = Field(
        ...,
        description="Complete HTML document body content",
        min_length=1,
    )
    assistant: str = Field(
        default="Applied requested changes.",
        description="Short note about applied changes",
    )
    meta: "EditMeta" = Field(default_factory=lambda: EditMeta())

    @field_validator("html")
    @classmethod
    def _strip_fences(cls, v: str) -> str:
        s = v.strip()
        if s.startswith("```"):
            import re

            s = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", s).strip()
            s = re.sub(r"\s*```$", "", s).strip()
        return s


class EditMeta(BaseModel):
    """Metadata about an edit operation."""

    model_config = ConfigDict(strict=False, extra="ignore")

    scope: Literal["selection", "document", "section", "unknown"] = Field(
        default="unknown"
    )
    preserved_structure: bool = Field(default=True)
    affected_sections: list[str] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)


class EditRiskAssessment(BaseModel):
    """Risk assessment for a proposed edit operation.

    Used by CrossChapterImpactAnalyzer to surface high-risk changes
    before they are applied.
    """

    model_config = ConfigDict(strict=False, extra="ignore")

    can_proceed: bool = Field(default=True)
    risk_level: Literal["none", "low", "medium", "high", "critical"] = Field(
        default="none"
    )
    issues: list[str] = Field(default_factory=list)
    broken_citation_keys: list[str] = Field(default_factory=list)
    orphaned_references: list[str] = Field(default_factory=list)
    affected_chapters: list[str] = Field(default_factory=list)
    suggested_mitigations: list[str] = Field(default_factory=list)


class RewriteIntent(BaseModel):
    """Parsed rewrite intent from natural-language instruction.

    Bridges free-text user instructions to structured editing operations.
    """

    model_config = ConfigDict(strict=False, extra="ignore")

    operation: Literal[
        "rewrite",
        "expand",
        "condense",
        "restructure",
        "insert",
        "delete",
        "merge",
        "split",
        "clarify",
        "unknown",
    ] = Field(default="unknown")
    target_sections: list[str] = Field(default_factory=list)
    target_paragraphs: list[int] = Field(default_factory=list)
    preserve_terms: list[str] = Field(default_factory=list)
    remove_terms: list[str] = Field(default_factory=list)
    add_citations: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    reasoning: str = Field(default="")


# Resolve forward refs
DocumentEditOutput.model_rebuild()
