"""Figure scoring and manifest helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from writing_agent.v2.diagram_design import enrich_figure_spec
from writing_agent.v2 import figure_render_quality_domain as quality_domain


def _figure_render_module():
    from writing_agent.v2 import figure_render as _figure_render

    return _figure_render


def _normalize_figure_type(spec: dict | None) -> str:
    return _figure_render_module()._normalize_figure_type(spec)


def extract_figure_specs(text: str, *, require_renderable: bool = False) -> list[dict[str, Any]]:
    figure_render = _figure_render_module()
    specs: list[dict[str, Any]] = []
    for idx, match in enumerate(figure_render._FIGURE_MARKER_RE.finditer(str(text or "")), start=1):
        raw = (match.group(1) or "").strip()
        spec = figure_render.safe_figure_spec_from_text(raw)
        if not isinstance(spec, dict):
            spec = {"raw": raw}
        spec.setdefault("caption", f"figure_{idx:03d}")
        spec = enrich_figure_spec(spec)
        if require_renderable and not is_renderable_figure_spec(spec):
            continue
        specs.append(spec)
    return specs


def _slugify_figure_caption(text: str, *, fallback: str) -> str:
    return quality_domain._slugify_figure_caption(text, fallback=fallback)


def _is_generic_caption(text: str) -> bool:
    return quality_domain._is_generic_caption(text)


def _score_caption(caption: str, issues: list[str]) -> int:
    return quality_domain._score_caption(caption, issues)


def _score_supported_type(kind: str, issues: list[str]) -> int:
    return quality_domain._score_supported_type(kind, issues)


def _as_list_safe(value: object) -> list:
    return quality_domain._as_list_safe(value)


def _figure_payload_has_meaningful_data(kind: str, data: dict | None) -> bool:
    return quality_domain._figure_payload_has_meaningful_data(kind, data)


def is_renderable_figure_spec(spec: dict | None) -> bool:
    return quality_domain.is_renderable_figure_spec(spec)


def _score_figure_data(kind: str, data: dict, issues: list[str]) -> int:
    return quality_domain._score_figure_data(kind, data, issues)


def _score_render_output(*, svg: str, png_rendered: bool) -> tuple[int, list[str]]:
    return quality_domain._score_render_output(svg=svg, png_rendered=png_rendered)


def _score_grade(score: int) -> str:
    return quality_domain._score_grade(score)


def _figure_semantic_text(kind: str, data: dict) -> str:
    return quality_domain._figure_semantic_text(kind, data)


def _score_caption_consistency(kind: str, caption: str, data: dict, issues: list[str]) -> int:
    return quality_domain._score_caption_consistency(kind, caption, data, issues)


def score_figure_spec(spec: dict, *, svg: str = "", png_rendered: bool = False) -> dict[str, Any]:
    return quality_domain.score_figure_spec(spec, svg=svg, png_rendered=png_rendered)


def _apply_figure_manifest_score_adjustments(items: list[dict[str, Any]]) -> None:
    quality_domain._apply_figure_manifest_score_adjustments(items)


def _figure_manifest_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    return quality_domain._figure_manifest_summary(items)


def _build_figure_manifest_from_specs(specs: list[dict[str, Any]], *, out_path: Path | None = None) -> dict[str, Any]:
    return quality_domain._build_figure_manifest_from_specs(specs, out_path=out_path)


def build_figure_score_manifest(text: str) -> dict[str, Any]:
    return quality_domain.build_figure_score_manifest(text)


def export_rendered_figure_assets(text: str, out_dir: str | Path) -> dict[str, Any]:
    return quality_domain.export_rendered_figure_assets(text, out_dir)


__all__ = [name for name in globals() if not name.startswith("__")]
