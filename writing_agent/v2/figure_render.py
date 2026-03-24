"""Figure rendering entrypoints and scoring exports."""

from __future__ import annotations

import html
import json
import re
from functools import lru_cache

try:
    import cairosvg
except Exception:  # pragma: no cover - optional dependency
    cairosvg = None

from writing_agent.v2.diagram_design import (
    enrich_figure_spec,
    render_flow_or_architecture_svg,
    render_professional_bar_svg,
    render_professional_er_svg,
    render_professional_line_svg,
    render_professional_pie_svg,
    render_professional_sequence_svg,
    render_professional_timeline_svg,
)

_FIGURE_MARKER_RE = re.compile(r"\[\[FIGURE\s*:\s*(\{[\s\S]*?\})\s*\]\]", flags=re.IGNORECASE)
_FILENAME_SANITIZE_RE = re.compile(r"[^0-9A-Za-z一-鿿._-]+")
_GENERIC_CAPTION_RE = re.compile(
    r"^(?:figure(?:_?\d+)?|fig(?:ure)?\s*\d*|chart\s*\d*|diagram\s*\d*|image\s*\d*|graphic\s*\d*)$",
    re.IGNORECASE,
)
_GENERIC_CAPTION_PREFIXES = ("?", "??", "???", "??", "??")
_FIGURE_FONT_STACK = "Microsoft YaHei, PingFang SC, Hiragino Sans GB, Noto Sans CJK SC, SimHei, SimSun, Arial Unicode MS, Segoe UI, Arial, sans-serif"
_FIGURE_RENDER_CACHE_VERSION = "20260313_pro_v2"
_SUPPORTED_FIGURE_TYPES = {
    "flow",
    "flowchart",
    "er",
    "bar",
    "bar_chart",
    "line",
    "line_chart",
    "pie",
    "pie_chart",
    "timeline",
    "sequence",
    "sequence_diagram",
    "architecture",
    "architecture_diagram",
    "arch",
}


def figure_png_renderer_available() -> bool:
    return cairosvg is not None


def _normalize_figure_type(spec: dict | None) -> str:
    raw = str((spec or {}).get("type") or "").strip().lower()
    aliases = {
        "bar_chart": "bar",
        "line_chart": "line",
        "pie_chart": "pie",
        "sequence_diagram": "sequence",
        "architecture_diagram": "architecture",
        "arch": "architecture",
    }
    return aliases.get(raw, raw) or "figure"


def _figure_spec_cache_payload(spec: dict | None) -> str:
    try:
        return json.dumps(
            {"version": _FIGURE_RENDER_CACHE_VERSION, "spec": spec or {}},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
    except Exception:
        return json.dumps({"version": _FIGURE_RENDER_CACHE_VERSION, "raw": str(spec or "")}, ensure_ascii=False, sort_keys=True)


def safe_figure_spec_from_text(raw: str) -> dict:
    try:
        payload = json.loads(raw)
        return payload if isinstance(payload, dict) else {"raw": raw}
    except Exception:
        return {"raw": raw}


@lru_cache(maxsize=128)
def _render_figure_bundle_cached(spec_payload: str, png_enabled: bool) -> tuple[str, bytes | None, str]:
    spec = safe_figure_spec_from_text(spec_payload)
    if isinstance(spec, dict) and "spec" in spec and isinstance(spec.get("spec"), dict):
        spec = spec.get("spec") or {}
    svg, caption = render_figure_svg(spec)
    png: bytes | None = None
    if png_enabled and cairosvg is not None:
        try:
            png = cairosvg.svg2png(bytestring=svg.encode("utf-8"))
        except Exception:
            png = None
    return svg, png, caption


def render_figure_bundle(spec: dict) -> tuple[str, bytes | None, str]:
    return _render_figure_bundle_cached(_figure_spec_cache_payload(spec), figure_png_renderer_available())


def render_figure_png(spec: dict) -> bytes | None:
    _svg, png, _caption = render_figure_bundle(spec)
    return png


from writing_agent.v2.figure_render_score_domain import (
    build_figure_score_manifest,
    export_rendered_figure_assets,
    extract_figure_specs,
    is_renderable_figure_spec,
    score_figure_spec,
)


def render_figure_svg(spec: dict) -> tuple[str, str]:
    spec = enrich_figure_spec(spec if isinstance(spec, dict) else {})
    figure_type = str((spec or {}).get("type") or "").strip().lower()
    caption = str((spec or {}).get("caption") or "").strip()
    data = (spec or {}).get("data") or {}
    payload = data if isinstance(data, dict) else {}

    if figure_type in {"flow", "flowchart", "architecture"}:
        resolved = caption or ("System Architecture" if figure_type == "architecture" else "Flow Diagram")
        return render_flow_or_architecture_svg(figure_type, caption, payload), resolved
    if figure_type == "er":
        return render_professional_er_svg(caption, payload), caption or "ER Diagram"
    if figure_type in {"bar", "bar_chart"}:
        return render_professional_bar_svg(caption, payload), caption or "Bar Chart"
    if figure_type in {"line", "line_chart"}:
        return render_professional_line_svg(caption, payload), caption or "Line Chart"
    if figure_type in {"pie", "pie_chart"}:
        return render_professional_pie_svg(caption, payload), caption or "Pie Chart"
    if figure_type == "timeline":
        return render_professional_timeline_svg(caption, payload), caption or "Timeline"
    if figure_type in {"sequence", "sequence_diagram"}:
        return render_professional_sequence_svg(caption, payload), caption or "Sequence Diagram"
    return _render_placeholder_svg(caption or f"Figure({figure_type or 'unknown'})"), caption or "Figure"


def _svg_wrap(inner: str, w: int, h: int, label: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        f'role="img" aria-label="{html.escape(label)}">'
        f'<style>text,tspan{{font-family:{_FIGURE_FONT_STACK};}}</style>'
        '<rect x="0" y="0" width="100%" height="100%" fill="#FFFFFF"/>'
        + inner
        + "</svg>"
    )


def _text(x: float, y: float, s: str, size: int = 12, anchor: str = "start", fill: str = "#1F2D3D") -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{anchor}" font-size="{size}" '
        f'fill="{fill}" font-family="{_FIGURE_FONT_STACK}">{html.escape(s or "")}</text>'
    )


def _render_placeholder_svg(caption: str, w: int = 760, h: int = 220) -> str:
    inner = (
        '<rect x="18" y="18" width="724" height="184" rx="14" ry="14" '
        'fill="#F6F8FC" stroke="#AEBBCD" stroke-width="1.2"/>'
        + _text(w / 2, h / 2, caption or "Figure", size=14, anchor="middle", fill="#2F5FA7")
    )
    return _svg_wrap(inner, w, h, caption or "figure")


__all__ = [name for name in globals() if not name.startswith("__")]
