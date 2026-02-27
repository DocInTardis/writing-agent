"""Export Settings Domain module.

This module belongs to `writing_agent.web.domains` in the writing-agent codebase.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Callable


def auto_export_template_enabled() -> bool:
    raw = str(os.environ.get("WRITING_AGENT_EXPORT_AUTO_TEMPLATE", "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def persist_export_autofix_enabled() -> bool:
    raw = str(os.environ.get("WRITING_AGENT_EXPORT_PERSIST_AUTOFIX", "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def resolve_export_template_path(
    session: Any,
    *,
    repo_root: Path,
    template_dir: Path,
    auto_export_template_enabled_fn: Callable[[], bool],
) -> str:
    template_path = str(getattr(session, "template_source_path", "") or "").strip()
    if template_path:
        path = Path(template_path)
        if path.suffix.lower() == ".docx" and path.exists():
            return str(path)
        template_path = ""
    env_template = str(os.environ.get("WRITING_AGENT_EXPORT_DEFAULT_TEMPLATE", "")).strip()
    if env_template:
        path = Path(env_template)
        if path.suffix.lower() == ".docx" and path.exists():
            return str(path)
    if not auto_export_template_enabled_fn():
        return ""
    try:
        for name in os.listdir(repo_root):
            if name.lower().endswith(".docx") and "converted" in name.lower():
                return str(repo_root / name)
        for name in os.listdir(template_dir):
            if re.search(r"\(1\)\.docx$", name):
                return str(template_dir / name)
        for name in os.listdir(template_dir):
            if name.lower().endswith(".docx") and "专业项目设计" in name:
                return str(template_dir / name)
    except Exception:
        return ""
    return ""


def formatting_from_session(
    session: Any,
    *,
    formatting_cls: Any,
) -> object:
    formatting = getattr(session, "formatting", None)
    if not isinstance(formatting, dict):
        return formatting_cls()
    try:
        font_size_pt = float(formatting.get("font_size_pt") or 10.5)
    except Exception:
        font_size_pt = 10.5
    try:
        line_spacing = float(formatting.get("line_spacing") or 1.5)
    except Exception:
        line_spacing = 1.5

    def _normalize_font_name(raw: object, fallback: str) -> str:
        name = str(raw or "").strip()
        if not name:
            return fallback
        fixes = {
            "宋体": "宋体",
            "黑体": "黑体",
            "SimSun": "宋体",
            "SimHei": "黑体",
        }
        return fixes.get(name, name)

    def _read_float(key: str) -> float | None:
        raw = formatting.get(key)
        if raw is None:
            return None
        try:
            return float(raw)
        except Exception:
            return None

    font_name = _normalize_font_name(formatting.get("font_name"), "瀹嬩綋")
    font_name_ea = _normalize_font_name(formatting.get("font_name_east_asia"), "瀹嬩綋")
    return formatting_cls(
        font_name=font_name,
        font_name_east_asia=font_name_ea,
        font_size_pt=font_size_pt,
        line_spacing=line_spacing,
        heading1_font_name=_normalize_font_name(formatting.get("heading1_font_name"), "榛戜綋") or None,
        heading1_font_name_east_asia=_normalize_font_name(formatting.get("heading1_font_name_east_asia"), "榛戜綋") or None,
        heading1_size_pt=_read_float("heading1_size_pt"),
        heading2_font_name=_normalize_font_name(formatting.get("heading2_font_name"), "榛戜綋") or None,
        heading2_font_name_east_asia=_normalize_font_name(formatting.get("heading2_font_name_east_asia"), "榛戜綋") or None,
        heading2_size_pt=_read_float("heading2_size_pt"),
        heading3_font_name=_normalize_font_name(formatting.get("heading3_font_name"), "榛戜綋") or None,
        heading3_font_name_east_asia=_normalize_font_name(formatting.get("heading3_font_name_east_asia"), "榛戜綋") or None,
        heading3_size_pt=_read_float("heading3_size_pt"),
    )


def export_prefs_from_session(
    session: Any,
    *,
    export_prefs_cls: Any,
) -> object:
    prefs = getattr(session, "generation_prefs", None)
    if not isinstance(prefs, dict):
        return export_prefs_cls()
    base_margin = float(prefs.get("page_margins_cm") or 2.8)
    return export_prefs_cls(
        include_cover=bool(prefs.get("include_cover", True)),
        include_toc=bool(prefs.get("include_toc", True)),
        toc_levels=int(prefs.get("toc_levels") or 3),
        include_header=bool(prefs.get("include_header", True)),
        page_numbers=bool(prefs.get("page_numbers", True)),
        header_text=str(prefs.get("header_text") or ""),
        footer_text=str(prefs.get("footer_text") or ""),
        page_margins_cm=base_margin,
        page_margin_top_cm=float(prefs.get("page_margin_top_cm") or 3.7),
        page_margin_bottom_cm=float(prefs.get("page_margin_bottom_cm") or 3.5),
        page_margin_left_cm=float(prefs.get("page_margin_left_cm") or 2.8),
        page_margin_right_cm=float(prefs.get("page_margin_right_cm") or 2.6),
        page_size=str(prefs.get("page_size") or "A4"),
    )
