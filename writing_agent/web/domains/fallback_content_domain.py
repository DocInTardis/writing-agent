"""Fallback Content Domain module.

This module belongs to `writing_agent.web.domains` in the writing-agent codebase.
"""

from __future__ import annotations

from typing import Any, Callable


def fallback_sections_from_session(
    session: Any,
    *,
    default_sections: list[str] | None = None,
) -> list[str]:
    if getattr(session, "template_outline", None):
        return [str(t or "").strip() for _, t in session.template_outline if str(t or "").strip()]
    if getattr(session, "template_required_h2", None):
        return [str(t or "").strip() for t in session.template_required_h2 if str(t or "").strip()]
    return list(default_sections or [])


def fallback_reference_items(
    session: Any,
    query: str,
    *,
    rag_list_papers: Callable[[], list[Any]],
    search_papers: Callable[..., list[Any]],
    format_reference_items: Callable[[list[dict]], list[str]],
) -> list[str]:
    q = (query or "").strip()
    if not q:
        q = str((getattr(session, "generation_prefs", {}) or {}).get("extra_requirements") or "").strip()
    if not q:
        q = str(getattr(session, "doc_text", "") or "").strip()
    papers = rag_list_papers()
    hits = search_papers(papers=papers, query=q, top_k=8)
    sources: list[dict] = []
    for h in hits:
        abs_url = str(getattr(h, "abs_url", "") or "")
        sources.append(
            {
                "title": str(getattr(h, "title", "") or ""),
                "url": abs_url,
                "authors": [],
                "published": getattr(h, "published", ""),
                "updated": getattr(h, "published", ""),
                "source": "openalex" if "openalex" in abs_url else "arxiv" if "arxiv" in abs_url else "",
            }
        )
    return format_reference_items(sources)


def build_fallback_text(
    title: str,
    sections: list[str],
    session: Any = None,
    *,
    is_reference_section: Callable[[str], bool],
    generic_fill_paragraph: Callable[..., str],
    merge_sections_text: Callable[[str, list[str], dict[str, str]], str],
    default_title: Callable[[], str],
    fallback_reference_items_fn: Callable[[Any, str], list[str]],
) -> str:
    fallback_text: dict[str, str] = {}
    ref_lines: list[str] = []
    if session is not None:
        query = str((getattr(session, "generation_prefs", {}) or {}).get("extra_requirements") or "").strip() or title
        ref_lines = fallback_reference_items_fn(session, query)
    for sec in sections:
        if is_reference_section(sec):
            fallback_text[sec] = "\n".join(ref_lines).strip()
        else:
            body = generic_fill_paragraph(sec, idx=1)
            if ref_lines:
                body = (body + " [1]").strip()
            fallback_text[sec] = body
    return merge_sections_text(title or default_title(), sections, fallback_text)


def augment_instruction(instruction: str, *, formatting: dict, generation_prefs: dict) -> str:
    inst = (instruction or "").strip()
    if not inst:
        return ""
    fmt = formatting if isinstance(formatting, dict) else {}
    prefs = generation_prefs if isinstance(generation_prefs, dict) else {}
    purpose = str(prefs.get("purpose") or "").strip()
    figure_types = prefs.get("figure_types")
    table_types = prefs.get("table_types")
    extra_req = str(prefs.get("extra_requirements") or "").strip()
    lines: list[str] = [inst, "", "【格式与输出约束（系统设置）】"]
    if purpose:
        lines.append(f"- 用途：{purpose}")
    mode = str(prefs.get("target_length_mode") or "").strip().lower()
    target_chars = int(prefs.get("target_char_count") or 0)
    target_pages = int(prefs.get("target_page_count") or 0)
    if mode == "pages" and target_pages > 0:
        lines.append(f"- 目标长度：约{target_pages}页（折合约{target_chars}字）")
    elif mode == "chars" and target_chars > 0:
        lines.append(f"- 目标长度：约{target_chars}字（折合约{target_pages}页）")
    if extra_req:
        lines.append(f"- 补充要求：{extra_req}")
    if fmt:
        name = str(fmt.get("font_size_name") or "").strip()
        pt = str(fmt.get("font_size_pt") or "").strip()
        ls = str(fmt.get("line_spacing") or "").strip()
        if name or pt:
            lines.append(f"- 字号：{name or '[默认]'}（{pt or '[默认]'}pt）")
        if ls:
            lines.append(f"- 行距：{ls}")
        h1_pt = str(fmt.get("heading1_size_pt") or "").strip()
        h2_pt = str(fmt.get("heading2_size_pt") or "").strip()
        h3_pt = str(fmt.get("heading3_size_pt") or "").strip()
        h1_font = str(fmt.get("heading1_font_name_east_asia") or fmt.get("heading1_font_name") or "").strip()
        h2_font = str(fmt.get("heading2_font_name_east_asia") or fmt.get("heading2_font_name") or "").strip()
        h3_font = str(fmt.get("heading3_font_name_east_asia") or fmt.get("heading3_font_name") or "").strip()
        if h1_pt or h1_font:
            lines.append(f"- 一级标题：{h1_font or '[默认字体]'} {h1_pt or '[默认字号]'}pt")
        if h2_pt or h2_font:
            lines.append(f"- 二级标题：{h2_font or '[默认字体]'} {h2_pt or '[默认字号]'}pt")
        if h3_pt or h3_font:
            lines.append(f"- 三级标题：{h3_font or '[默认字体]'} {h3_pt or '[默认字号]'}pt")
    if isinstance(table_types, list) and table_types:
        lines.append("- 建议表格类型：" + ", ".join([str(x) for x in table_types]))
    if isinstance(figure_types, list) and figure_types:
        lines.append("- 建议图类型：" + ", ".join([str(x) for x in figure_types]))
    lines.append("- 若缺少具体数据，请使用保守描述，不要输出占位提示。")
    lines.append("- 输出应可直接提交，不要出现提示语、草稿说明或AI痕迹。")
    lines.append("- 正文避免无关符号或标记（标题行除外）。")
    return "\n".join([x for x in lines if x is not None]).strip()
