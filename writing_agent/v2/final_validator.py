"""Final document validator with dual-pass gate semantics."""

from __future__ import annotations

from writing_agent.v2 import final_validator_gate_domain as gate_domain
from writing_agent.v2.final_validator_metrics_domain import *


def validate_final_document(
    *,
    title: str,
    text: str,
    sections: list[str],
    problems: list[str],
    rag_gate_dropped: list[dict] | None = None,
    figure_manifest: dict[str, object] | None = None,
    source_rows: list[dict] | None = None,
) -> dict[str, object]:
    return gate_domain.validate_final_document(
        title=title,
        text=text,
        sections=sections,
        problems=problems,
        rag_gate_dropped=rag_gate_dropped,
        figure_manifest=figure_manifest,
        source_rows=source_rows,
    )


__all__ = [name for name in globals() if not name.startswith('__')]
