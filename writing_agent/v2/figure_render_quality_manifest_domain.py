"""Figure quality manifest helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from writing_agent.v2.diagram_design import enrich_figure_spec
from writing_agent.v2 import figure_render_quality_data_domain as data_domain
from writing_agent.v2 import figure_render_quality_scoring_domain as scoring_domain


def _base():
    from writing_agent.v2 import figure_render_quality_domain as base

    return base


def _apply_figure_manifest_score_adjustments(items: list[dict[str, Any]]) -> None:
    seen: dict[tuple[str, str], int] = {}
    for item in items:
        kind = str(item.get("type") or "").strip().lower()
        caption = str(item.get("caption") or "").strip().casefold()
        if not caption:
            continue
        key = (kind, caption)
        duplicate_index = seen.get(key, 0)
        seen[key] = duplicate_index + 1
        if duplicate_index <= 0:
            continue
        item["score"] = max(0, int(item.get("score") or 0) - 12)
        issues = [str(x).strip() for x in (item.get("issues") or []) if str(x).strip()]
        if "duplicate_caption" not in issues:
            issues.append("duplicate_caption")
        breakdown = item.get("breakdown") if isinstance(item.get("breakdown"), dict) else {}
        penalties = breakdown.get("penalties") if isinstance(breakdown.get("penalties"), dict) else {}
        penalties["duplicate_caption"] = 12
        breakdown["penalties"] = penalties
        item["breakdown"] = breakdown
        item["issues"] = issues
        item["grade"] = scoring_domain._score_grade(int(item.get("score") or 0))
        item["passed"] = bool(int(item.get("score") or 0) >= 60)
        item["recommendation"] = "keep" if int(item.get("score") or 0) >= 75 else ("review" if int(item.get("score") or 0) >= 55 else "drop")


def _figure_manifest_summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    scores = [int(item.get("score") or 0) for item in items]
    passed_count = sum(1 for item in items if bool(item.get("passed")))
    review_count = sum(1 for item in items if str(item.get("recommendation") or "") == "review")
    drop_count = sum(1 for item in items if str(item.get("recommendation") or "") == "drop")
    return {
        "avg_score": round(sum(scores) / len(scores), 2) if scores else 0.0,
        "min_score": min(scores) if scores else 0,
        "max_score": max(scores) if scores else 0,
        "passed_count": int(passed_count),
        "review_count": int(review_count),
        "drop_count": int(drop_count),
    }


def _build_figure_manifest_from_specs(specs: list[dict[str, Any]], *, out_path: Path | None = None) -> dict[str, Any]:
    figure_render = data_domain._figure_render_module()
    items: list[dict[str, Any]] = []
    resolved_out_path = out_path.resolve() if out_path is not None else None
    if resolved_out_path is not None:
        resolved_out_path.mkdir(parents=True, exist_ok=True)
    for idx, spec in enumerate(specs, start=1):
        render_spec = enrich_figure_spec(spec if isinstance(spec, dict) else {})
        svg, png, caption = figure_render.render_figure_bundle(render_spec)
        kind = data_domain._normalize_figure_type(render_spec)
        scored_spec = dict(render_spec or {})
        if caption and not str(scored_spec.get("caption") or "").strip():
            scored_spec["caption"] = caption
        score = scoring_domain.score_figure_spec(scored_spec, svg=svg, png_rendered=bool(png))
        item: dict[str, Any] = {
            "index": idx,
            "type": kind,
            "caption": caption,
            "png_rendered": bool(png),
            **score,
        }
        if resolved_out_path is not None:
            stem = f"fig_{idx:03d}_{data_domain._slugify_figure_caption(caption, fallback=kind)}"
            svg_path = resolved_out_path / f"{stem}.svg"
            svg_path.write_text(svg, encoding="utf-8")
            png_file = ""
            if png:
                png_path = resolved_out_path / f"{stem}.png"
                png_path.write_bytes(png)
                png_file = str(png_path)
            item["svg_file"] = str(svg_path)
            item["png_file"] = png_file
        items.append(item)
    _apply_figure_manifest_score_adjustments(items)
    manifest = {
        "count": len(items),
        "png_renderer_available": figure_render.figure_png_renderer_available(),
        **_figure_manifest_summary(items),
        "items": items,
    }
    if resolved_out_path is not None:
        manifest["output_dir"] = str(resolved_out_path)
    return manifest


def build_figure_score_manifest(text: str) -> dict[str, Any]:
    return _build_figure_manifest_from_specs(_base().extract_figure_specs(text), out_path=None)


def export_rendered_figure_assets(text: str, out_dir: str | Path) -> dict[str, Any]:
    out_path = Path(out_dir).resolve()
    manifest = _build_figure_manifest_from_specs(_base().extract_figure_specs(text), out_path=out_path)
    (out_path / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


__all__ = [name for name in globals() if not name.startswith("__")]
