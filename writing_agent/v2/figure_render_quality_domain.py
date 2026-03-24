"""Figure quality scoring and manifest generation helpers."""

from __future__ import annotations

from typing import Any

from writing_agent.v2 import figure_render_quality_data_domain as data_domain
from writing_agent.v2 import figure_render_quality_manifest_domain as manifest_domain
from writing_agent.v2 import figure_render_quality_scoring_domain as scoring_domain


def _base():
    from writing_agent.v2 import figure_render_score_domain as base

    return base


def _figure_render_module():
    return _base()._figure_render_module()


def _normalize_figure_type(spec: dict | None) -> str:
    return _base()._normalize_figure_type(spec)


def extract_figure_specs(text: str, *, require_renderable: bool = False) -> list[dict[str, Any]]:
    return _base().extract_figure_specs(text, require_renderable=require_renderable)


_slugify_figure_caption = data_domain._slugify_figure_caption
_is_generic_caption = data_domain._is_generic_caption
_score_caption = data_domain._score_caption
_score_supported_type = data_domain._score_supported_type
_as_list_safe = data_domain._as_list_safe
_figure_payload_has_meaningful_data = data_domain._figure_payload_has_meaningful_data
is_renderable_figure_spec = data_domain.is_renderable_figure_spec
_score_figure_data = data_domain._score_figure_data
_score_render_output = scoring_domain._score_render_output
_score_grade = scoring_domain._score_grade
_figure_semantic_text = scoring_domain._figure_semantic_text
_score_caption_consistency = scoring_domain._score_caption_consistency
score_figure_spec = scoring_domain.score_figure_spec
_apply_figure_manifest_score_adjustments = manifest_domain._apply_figure_manifest_score_adjustments
_figure_manifest_summary = manifest_domain._figure_manifest_summary
_build_figure_manifest_from_specs = manifest_domain._build_figure_manifest_from_specs
build_figure_score_manifest = manifest_domain.build_figure_score_manifest
export_rendered_figure_assets = manifest_domain.export_rendered_figure_assets


__all__ = [name for name in globals() if not name.startswith("__")]
