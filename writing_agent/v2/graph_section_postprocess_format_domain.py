"""Section postprocess formatting helpers."""

from __future__ import annotations

import json
import re
from collections.abc import Callable

from writing_agent.v2.diagram_design import enrich_figure_spec
from writing_agent.v2.figure_render import is_renderable_figure_spec

def strip_inline_headings(
    text: str,
    section_title: str,
    *,
    looks_like_heading_text: Callable[[str], bool],
) -> str:
    lines = []
    for line in (text or "").splitlines():
        token = line.strip()
        if not token:
            lines.append("")
            continue
        if re.match(r"^#{1,6}$", token):
            continue
        is_heading = False
        if re.match(r"^\s*#{1,6}\s+", token):
            is_heading = True
            token = re.sub(r"^\s*#{1,6}\s+", "", token).strip()
        if re.match(r"^第\s*\d+\s*[章节]\s*", token):
            is_heading = True
            token = re.sub(r"^第\s*\d+\s*[章节]\s*", "", token).strip()
        if section_title and token == section_title:
            continue
        if re.match(r"^[一二三四五六七八九十]+[、.]\s*", token):
            is_heading = True
            token = re.sub(r"^[一二三四五六七八九十]+[、.]\s*", "", token).strip()
        if re.match(r"^\d+(?:\.\d+)*\s+", token):
            is_heading = True
            token = re.sub(r"^\d+(?:\.\d+)*\s+", "", token).strip()
        if not token:
            continue
        if is_heading:
            continue
        if len(token) <= 10 and not re.search(r"[。！？；:：!?]", token) and looks_like_heading_text(token):
            continue
        lines.append(token)
    return "\n".join(lines).strip()

def format_references(text: str, *, strip_markdown_noise: Callable[[str], str]) -> str:
    raw = (text or "").replace("\r", "")
    raw = strip_markdown_noise(raw)
    lines = []
    for line in raw.splitlines():
        token = line.strip()
        if not token:
            continue
        if "引用格式" in token or "格式示例" in token:
            continue
        token = re.sub(r"^\s*[-*\u2022]\s+", "", token)
        token = re.sub(r"^\s*\d+\.\s*", "", token)
        token = re.sub(r"^\s*\[(?:\d+)\]\s*", "", token)
        token = token.strip()
        if token:
            lines.append(token)

    if not lines:
        return ""
    merged: list[str] = []
    for line in lines:
        if merged and (len(line) <= 8 or re.fullmatch(r"[\d\W]+", line)):
            merged[-1] = (merged[-1].rstrip(".。;；") + " " + line).strip()
        else:
            merged.append(line)
    out: list[str] = []
    for i, line in enumerate(merged, 1):
        out.append(f"[{i}] {line}")
    return "\n\n".join(out)

def ensure_media_markers(
    text: str,
    *,
    section_title: str,
    min_tables: int,
    min_figures: int,
    is_reference_section: Callable[[str], bool],
) -> str:
    _ = (min_tables, min_figures)
    if not text:
        return text
    if is_reference_section(section_title):
        return text

    def _drop_invalid_figure(match: re.Match[str]) -> str:
        raw = str(match.group(1) or "").strip()
        try:
            payload = json.loads(raw) if raw else {}
        except Exception:
            return ""
        if not isinstance(payload, dict):
            return ""
        if not is_renderable_figure_spec(payload):
            return ""
        payload = enrich_figure_spec(payload, section_title=section_title)
        if not is_renderable_figure_spec(payload):
            return ""
        return f"[[FIGURE:{json.dumps(payload, ensure_ascii=False)}]]"

    text = re.sub(r"\[\[\s*FIGURE\s*:\s*(\{[\s\S]*?\})\s*\]\]", _drop_invalid_figure, text, flags=re.IGNORECASE)
    return text.strip()

def _normalize_media_markers(text: str, *, section_title: str) -> str:
    src = str(text or "")
    if not src:
        return src

    def _normalize_table(match: re.Match[str]) -> str:
        raw = str(match.group(1) or "").strip()
        try:
            payload = json.loads(raw) if raw else {}
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        caption = str(payload.get("caption") or "").strip()
        if not caption:
            caption = f"{section_title}关键指标对比"
        rows = payload.get("rows")
        if not isinstance(rows, list):
            rows = []
        value_cells: list[str] = []
        for row in rows:
            if isinstance(row, list):
                cells = [str(c).strip() for c in row]
                if len(cells) > 1:
                    value_cells.extend(cells[1:])
                else:
                    value_cells.extend(cells)
        if value_cells and all(c in {"--", "-", ""} for c in value_cells):
            rows = [
                ["数据可信性", "依赖中心化校验，跨主体核验成本高", "链上校验与多方共识降低篡改风险"],
                ["服务响应效率", "流程环节多，跨部门协同时延高", "流程标准化后可缩短处理链路"],
                ["治理透明度", "状态追踪分散，责任定位困难", "关键流程可追踪，便于审计复核"],
            ]
            payload["columns"] = ["评价维度", "现有方案", "本研究方案"]
        payload["caption"] = caption
        payload["rows"] = rows
        return f"[[TABLE:{json.dumps(payload, ensure_ascii=False)}]]"

    def _normalize_figure(match: re.Match[str]) -> str:
        raw = str(match.group(1) or "").strip()
        try:
            payload = json.loads(raw) if raw else {}
        except Exception:
            payload = {}
        if not isinstance(payload, dict):
            payload = {}
        payload = enrich_figure_spec(payload, section_title=section_title, context_text=section_title)
        if not is_renderable_figure_spec(payload):
            return ""
        caption = str(payload.get("caption") or "").strip()
        if (not caption) or (caption in {"\u65b9\u6cd5\u6d41\u7a0b\u56fe", "\u4e1a\u52a1\u6d41\u7a0b\u793a\u610f\u56fe", "\u6d41\u7a0b\u56fe", "\u5173\u952e\u6d41\u7a0b\u793a\u610f\u56fe"}):
            payload["caption"] = f"{section_title}\u6d41\u7a0b\u793a\u610f\u56fe"
        payload = enrich_figure_spec(payload, section_title=section_title, context_text=caption or section_title)
        return f"[[FIGURE:{json.dumps(payload, ensure_ascii=False)}]]"

    src = re.sub(r"\[\[\s*TABLE\s*:\s*(\{[\s\S]*?\})\s*\]\]", _normalize_table, src, flags=re.IGNORECASE)
    src = re.sub(r"\[\[\s*FIGURE\s*:\s*(\{[\s\S]*?\})\s*\]\]", _normalize_figure, src, flags=re.IGNORECASE)
    return src

__all__ = [name for name in globals() if not name.startswith('__')]
