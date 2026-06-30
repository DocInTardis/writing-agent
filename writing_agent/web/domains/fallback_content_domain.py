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
    lines: list[str] = [inst, "", "【输出约束（系统设置）】"]
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
        lines.append("- 排版会在导出阶段自动应用；不要把字体、字号、行距、目录、页眉页脚等设置写入正文。")
        lines.append("- 题目必须围绕主题自行拟定，不要把排版参数、样式名称或模板标签当作标题。")
    if isinstance(table_types, list) and table_types:
        lines.append("- 建议表格类型：" + ", ".join([str(x) for x in table_types]))
    if isinstance(figure_types, list) and figure_types:
        lines.append("- 建议图类型：" + ", ".join([str(x) for x in figure_types]))
    lines.append("- 若缺少具体数据，请使用保守描述，不要输出占位提示。")
    lines.append("- 输出应可直接提交，不要出现提示语、草稿说明或AI痕迹。")
    lines.append("- 正文避免无关符号或标记（标题行除外）。")
    return "\n".join([x for x in lines if x is not None]).strip()
