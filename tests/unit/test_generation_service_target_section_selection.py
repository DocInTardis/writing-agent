from __future__ import annotations

from writing_agent.web.services.generation_service import GenerationService


def _norm(text: object) -> str:
    return str(text or "").strip().lower().replace(" ", "")


def test_resolve_target_section_selection_returns_section_body_span() -> None:
    text = "# T\n\n## Introduction\n\nAlpha body.\nStill intro.\n\n## Conclusion\n\nOmega body.\n"
    out = GenerationService._resolve_target_section_selection(
        text=text,
        section_title="Introduction",
        normalize_heading_text=_norm,
    )
    assert out is not None
    assert out["title"] == "Introduction"
    assert out["text"] == "Alpha body.\nStill intro."
    start = int(out["start"])
    end = int(out["end"])
    assert text.replace("\r\n", "\n").replace("\r", "\n")[start:end].strip("\n") == "Alpha body.\nStill intro."


def test_resolve_target_section_selection_falls_back_to_heading_when_body_empty() -> None:
    text = "# T\n\n## Introduction\n\n## Conclusion\n\nOmega body.\n"
    out = GenerationService._resolve_target_section_selection(
        text=text,
        section_title="Introduction",
        normalize_heading_text=_norm,
    )
    assert out is not None
    assert "## Introduction" in str(out["text"])


def test_resolve_target_section_selection_returns_none_for_missing_section() -> None:
    text = "# T\n\n## Introduction\n\nAlpha body.\n"
    out = GenerationService._resolve_target_section_selection(
        text=text,
        section_title="Conclusion",
        normalize_heading_text=_norm,
    )
    assert out is None
