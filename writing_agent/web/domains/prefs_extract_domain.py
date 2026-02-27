"""Prefs Extract Domain module.

This module belongs to `writing_agent.web.domains` in the writing-agent codebase.
"""

from __future__ import annotations

import re


def coerce_float(value: object) -> float | None:
    try:
        return float(value)
    except Exception:
        return None


def coerce_int(value: object) -> int | None:
    try:
        return int(float(value))
    except Exception:
        return None


def _normalize_fullwidth_digits(text: str) -> str:
    trans = str.maketrans(
        {
            "０": "0",
            "１": "1",
            "２": "2",
            "３": "3",
            "４": "4",
            "５": "5",
            "６": "6",
            "７": "7",
            "８": "8",
            "９": "9",
            "：": ":",
            "，": ",",
            "；": ";",
        }
    )
    return str(text or "").translate(trans)


def _extract_title(norm: str) -> str:
    patterns = [
        r"(?:生成|撰写|写一份|做一份|准备一份)\s*([^\n,;]{2,40}?)(?:报告|论文|方案|设计|说明书)",
        r"主题[:：]\s*([^\n,;]{2,40})",
        r"题目[:：]\s*([^\n,;]{2,40})",
    ]
    for pat in patterns:
        m = re.search(pat, norm, flags=re.IGNORECASE)
        if m:
            title = str(m.group(1) or "").strip()
            title = re.sub(r"(关于|围绕)$", "", title).strip()
            if title:
                return title
    return ""


def _extract_target_length(norm: str) -> tuple[str, int] | None:
    m_wan_chars = re.search(r"(\d+(?:\.\d+)?)\s*万\s*字", norm)
    if m_wan_chars:
        return "chars", int(float(m_wan_chars.group(1)) * 10000)

    m_chars = re.search(r"(\d{2,7})\s*(?:字|字符)", norm)
    if m_chars:
        return "chars", int(m_chars.group(1))

    m_pages = re.search(r"(\d{1,3})\s*(?:页|面)", norm)
    if m_pages:
        return "pages", int(m_pages.group(1))
    return None


def fast_extract_prefs(text: str) -> dict:
    raw = str(text or "").strip()
    if not raw:
        return {}
    norm = _normalize_fullwidth_digits(raw)

    result: dict = {}
    formatting: dict = {}
    prefs: dict = {}

    title = _extract_title(norm)
    if title:
        result["title"] = title

    length_row = _extract_target_length(norm)
    if length_row:
        mode, value = length_row
        prefs["target_length_mode"] = mode
        prefs["target_length_value"] = int(value)

    m_font = re.search(r"(?:正文字体|字体)\s*[:: ]\s*([A-Za-z ]{3,30}|[\u4e00-\u9fff]{2,12})", norm)
    if m_font:
        font_name = str(m_font.group(1) or "").strip()
        if font_name:
            formatting["font_name_east_asia"] = font_name

    size_map = {"五号": 10.5, "小四": 12, "四号": 14, "小三": 15, "三号": 16, "小二": 18, "二号": 22}
    m_size_name = re.search(r"(?:字号|正文字号)\s*[:: ]\s*(五号|小四|四号|小三|三号|小二|二号)", norm)
    if m_size_name:
        size_name = str(m_size_name.group(1) or "").strip()
        if size_name in size_map:
            formatting["font_size_name"] = size_name
            formatting["font_size_pt"] = size_map[size_name]
    else:
        m_size_pt = re.search(r"(?:字号|正文字号)\s*[:: ]\s*(\d+(?:\.\d+)?)\s*pt", norm, flags=re.IGNORECASE)
        if m_size_pt:
            formatting["font_size_pt"] = float(m_size_pt.group(1))

    m_line = re.search(r"(?:行距|行间距)\s*[:: ]\s*(\d+(?:\.\d+)?)", norm)
    if m_line:
        formatting["line_spacing"] = float(m_line.group(1))

    if re.search(r"(?:不要|无需|取消)\s*封面", norm):
        prefs["include_cover"] = False
    elif re.search(r"(?:需要|包含|有)\s*封面", norm):
        prefs["include_cover"] = True

    if re.search(r"(?:不要|无需|取消)\s*目录", norm):
        prefs["include_toc"] = False
    elif re.search(r"(?:需要|包含|有)\s*目录", norm):
        prefs["include_toc"] = True

    if re.search(r"(?:不要|无需|取消)\s*(?:页码|页数)", norm):
        prefs["page_numbers"] = False
    elif re.search(r"(?:需要|包含|有)\s*(?:页码|页数)", norm):
        prefs["page_numbers"] = True

    if re.search(r"\bA5\b", norm, flags=re.IGNORECASE):
        prefs["page_size"] = "A5"
    elif re.search(r"\bA4\b", norm, flags=re.IGNORECASE):
        prefs["page_size"] = "A4"
    elif re.search(r"\bLETTER\b", norm, flags=re.IGNORECASE):
        prefs["page_size"] = "LETTER"

    m_margin = re.search(r"(?:页边距|页面边距)\s*[:: ]\s*(\d+(?:\.\d+)?)\s*cm", norm, flags=re.IGNORECASE)
    if m_margin:
        prefs["page_margins_cm"] = float(m_margin.group(1))

    if formatting:
        result["formatting"] = formatting
    if prefs:
        result["generation_prefs"] = prefs
    if result:
        result["summary"] = "已识别标题、篇幅与部分排版要求。"
    return result


def normalize_ai_formatting(data: object) -> dict:
    if not isinstance(data, dict):
        return {}
    out: dict = {}

    def _set_str(key: str) -> None:
        val = str(data.get(key) or "").strip()
        if val:
            out[key] = val

    _set_str("font_name")
    _set_str("font_name_east_asia")
    _set_str("font_size_name")
    _set_str("heading1_font_name")
    _set_str("heading1_font_name_east_asia")
    _set_str("heading2_font_name")
    _set_str("heading2_font_name_east_asia")
    _set_str("heading3_font_name")
    _set_str("heading3_font_name_east_asia")

    fs_pt = coerce_float(data.get("font_size_pt"))
    if fs_pt:
        out["font_size_pt"] = fs_pt
    if "font_size_pt" not in out:
        size_name = str(out.get("font_size_name") or "").strip()
        name_map = {"五号": 10.5, "小四": 12, "四号": 14, "小三": 15, "三号": 16, "小二": 18, "二号": 22}
        if size_name in name_map:
            out["font_size_pt"] = name_map[size_name]

    ls = coerce_float(data.get("line_spacing"))
    if ls:
        out["line_spacing"] = ls
    h1_pt = coerce_float(data.get("heading1_size_pt"))
    if h1_pt:
        out["heading1_size_pt"] = h1_pt
    h2_pt = coerce_float(data.get("heading2_size_pt"))
    if h2_pt:
        out["heading2_size_pt"] = h2_pt
    h3_pt = coerce_float(data.get("heading3_size_pt"))
    if h3_pt:
        out["heading3_size_pt"] = h3_pt
    return out


def replace_question_headings(text: str) -> str:
    if not text:
        return str(text or "")
    lines = []
    for line in str(text).replace("\r", "").split("\n"):
        if re.match(r"^#{1,3}\s*[?？]{2,}\s*$", line):
            line = "## 参考文献"
        elif re.match(r"^[?？]{2,}\s*$", line):
            line = "参考文献"
        lines.append(line)
    return "\n".join(lines)


def normalize_ai_prefs(data: object) -> dict:
    if not isinstance(data, dict):
        return {}
    out: dict = {}
    purpose = str(data.get("purpose") or "").strip()
    if purpose:
        out["purpose"] = purpose

    mode = str(data.get("target_length_mode") or "").strip().lower()
    if mode in {"chars", "pages"}:
        out["target_length_mode"] = mode
        val = coerce_int(data.get("target_length_value"))
        if val and val > 0:
            out["target_length_value"] = val

    if isinstance(data.get("expand_outline"), bool):
        out["expand_outline"] = bool(data.get("expand_outline"))
    for key in ("include_cover", "include_toc", "include_header", "page_numbers"):
        if isinstance(data.get(key), bool):
            out[key] = bool(data.get(key))

    page_size = str(data.get("page_size") or "").strip().upper()
    if page_size in {"A4", "A5", "LETTER"}:
        out["page_size"] = page_size
    margin = coerce_float(data.get("page_margins_cm"))
    if margin and margin > 0:
        out["page_margins_cm"] = margin

    for key in ("header_text", "footer_text", "audience", "output_form", "voice", "avoid", "scope"):
        val = str(data.get(key) or "").strip()
        if val:
            out[key] = val
    return out
