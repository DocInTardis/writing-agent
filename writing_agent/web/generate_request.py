"""Generate Request module.

This module belongs to `writing_agent.web` in the writing-agent codebase.
"""

from __future__ import annotations

import re
from typing import Callable


_SECTION_TOKEN_EXTRACT_RE = re.compile(r"^H[23]::\s*(.*)$", re.IGNORECASE)
_FORMAT_ONLY_PREF_KEYS = {
    "include_cover",
    "include_toc",
    "include_header",
    "page_numbers",
    "page_size",
    "page_margins_cm",
    "header_text",
    "footer_text",
}
_FORMAT_ONLY_HINT_RE = re.compile(
    r"(字体|字号|字重|行距|行间距|首行缩进|缩进|对齐|段前|段后|"
    r"排版|样式|格式|页边距|页眉|页脚|页码|目录|封面|纸张|A4|A5|LETTER)",
    flags=re.IGNORECASE,
)
_CONTENT_REWRITE_HINT_RE = re.compile(
    r"(重写|改写|润色|优化|扩写|缩写|精简|压缩|提炼|总结|概述|翻译|"
    r"补充(?:内容|章节|段落)|新增(?:内容|章节|段落)|删除(?:内容|章节|段落)|"
    r"合并章节|拆分章节|重排|排序|生成|撰写|写一(?:篇|份)?)"
)


def normalize_resume_sections(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        sec = str(item or "").strip()
        if not sec or sec in seen:
            continue
        seen.add(sec)
        out.append(sec)
    return out


def apply_resume_sections_instruction(
    instruction: str,
    resume_sections: list[str],
    *,
    cursor_anchor: str = "",
) -> str:
    raw = str(instruction or "").strip()
    if not raw:
        return raw
    sections = normalize_resume_sections(resume_sections)
    if not sections and not cursor_anchor:
        return raw
    if sections:
        sec_text = "、".join(sections)
        guard = (
            "这是断点续写任务。"
            f"仅补写以下未完成章节：{sec_text}。"
            "不要改写已完成章节，也不要重排目录顺序。"
        )
    else:
        guard = (
            "这是断点续写任务。"
            "请从指定锚点继续补写，不要改写已完成章节。"
        )
    if cursor_anchor:
        guard += f" 续写锚点：{cursor_anchor}。"
    if guard in raw:
        return raw
    return f"{guard}\n\n用户需求：{raw}"


def normalize_compose_mode(value: object) -> str:
    mode = str(value or "").strip().lower()
    if mode in {"continue", "overwrite", "auto"}:
        return mode
    return "auto"


def apply_compose_mode_instruction(instruction: str, compose_mode: str, *, has_existing: bool) -> str:
    raw = str(instruction or "").strip()
    if not raw:
        return raw
    mode = normalize_compose_mode(compose_mode)
    if mode == "auto" or not has_existing:
        return raw
    if mode == "continue":
        guard = "请在保留现有内容结构和已写段落的前提下继续写作，不要删除或改写已有内容。"
        if guard in raw:
            return raw
        return f"{guard}\n\n用户需求：{raw}"
    if mode == "overwrite":
        guard = "请忽略当前已有正文，按用户需求从头完整重写，并用新内容覆盖旧内容。"
        if guard in raw:
            return raw
        return f"{guard}\n\n用户需求：{raw}"
    return raw


def decode_section_title_for_stream(section: str) -> str:
    raw = str(section or "").strip()
    if not raw:
        return ""
    match = _SECTION_TOKEN_EXTRACT_RE.match(raw)
    return (match.group(1) if match else raw).strip()


def normalize_section_key_for_stream(section_title: str) -> str:
    text = decode_section_title_for_stream(section_title)
    text = re.sub(r"^#+\s*", "", text).strip().lower()
    text = re.sub(r"[^\w\u4e00-\u9fff]+", "", text, flags=re.UNICODE)
    return text


def looks_like_modify_instruction(raw: str) -> bool:
    s = (raw or "").strip()
    if not s:
        return False
    compact = re.sub(r"\s+", "", s)
    if re.search(
        r"(修改|润色|改写|重写|优化|调整|替换|改为|改成|删减|删除|去掉|补充|扩写|简化|校对|纠错|统一|合并|拆分|分拆|分成|新增|添加|插入|移动|移到|放到|重排|排序|顺序|交换|互换|对调)",
        compact,
    ):
        return True
    if re.search(r"(把|将).{1,80}(改为|改成|替换为|换成|移到|放到).{1,80}", compact):
        return True
    if re.search(r"(标题|题目).{0,6}(改为|改成|调整|设置)", compact):
        return True
    if re.search(r"(删除|移除|去掉).{0,8}(章节|小节|部分|标题)", compact):
        return True
    if re.search(r"(合并|拆分|分拆|分成|交换|互换|对调).{1,20}(章节|小节|部分)", compact):
        return True
    return False


def extract_format_only_updates(
    raw: str,
    analysis: dict | None = None,
    *,
    parse_prefs: Callable[[str], dict],
    normalize_formatting: Callable[[object], dict],
    normalize_prefs: Callable[[object], dict],
) -> dict | None:
    text = str(raw or "").strip()
    if not text:
        return None
    compact = re.sub(r"\s+", "", text)
    parsed = parse_prefs(text)
    fmt = normalize_formatting(parsed.get("formatting") if isinstance(parsed, dict) else None)
    for key in (
        "font_name",
        "font_name_east_asia",
        "heading1_font_name",
        "heading1_font_name_east_asia",
        "heading2_font_name",
        "heading2_font_name_east_asia",
        "heading3_font_name",
        "heading3_font_name_east_asia",
    ):
        val = str(fmt.get(key) or "").strip()
        if not val:
            continue
        cleaned = re.sub(r"^(?:改为|改成|设置为|设为|调整为|换成|统一为|使用)", "", val).strip()
        cleaned = re.sub(r"[，。！？；：:,.].*$", "", cleaned).strip()
        if cleaned:
            fmt[key] = cleaned
        else:
            fmt.pop(key, None)
    prefs_all = normalize_prefs(parsed.get("generation_prefs") if isinstance(parsed, dict) else None)
    prefs = {k: v for k, v in prefs_all.items() if k in _FORMAT_ONLY_PREF_KEYS}
    has_values = bool(fmt or prefs)
    style_hint = bool(_FORMAT_ONLY_HINT_RE.search(compact))
    intent_name = ""
    intent_conf = 0.0
    entity_formatting = ""
    if isinstance(analysis, dict):
        intent = analysis.get("intent")
        if isinstance(intent, dict):
            intent_name = str(intent.get("name") or "").strip().lower()
            try:
                intent_conf = float(intent.get("confidence") or 0)
            except Exception:
                intent_conf = 0.0
        entities = analysis.get("entities")
        if isinstance(entities, dict):
            entity_formatting = str(entities.get("formatting") or "").strip()
    analysis_supports_format = (
        (intent_name == "format" and intent_conf >= 0.35)
        or (intent_name == "template" and intent_conf >= 0.45)
        or bool(entity_formatting)
    )
    if not (has_values or style_hint or analysis_supports_format):
        return None
    if _CONTENT_REWRITE_HINT_RE.search(compact):
        return None
    if intent_name in {"generate", "outline"} and intent_conf >= 0.6 and not has_values:
        return None
    return {"formatting": fmt, "generation_prefs": prefs, "has_values": has_values}


def try_format_only_update(
    session,
    instruction: str,
    analysis: dict | None = None,
    *,
    extract_updates: Callable[[str, dict | None], dict | None],
) -> str | None:
    parsed = extract_updates(instruction, analysis)
    if not parsed:
        return None
    fmt_update = parsed.get("formatting") if isinstance(parsed.get("formatting"), dict) else {}
    pref_update = parsed.get("generation_prefs") if isinstance(parsed.get("generation_prefs"), dict) else {}
    has_values = bool(parsed.get("has_values"))
    changed = False
    next_fmt = dict(getattr(session, "formatting", {}) or {})
    for key, value in fmt_update.items():
        if next_fmt.get(key) != value:
            next_fmt[key] = value
            changed = True
    next_prefs = dict(getattr(session, "generation_prefs", {}) or {})
    for key, value in pref_update.items():
        if next_prefs.get(key) != value:
            next_prefs[key] = value
            changed = True
    if changed:
        session.formatting = next_fmt
        session.generation_prefs = next_prefs
        return "已更新格式设置，正文保持不变。"
    if has_values:
        return "格式设置与当前一致，正文保持不变。"
    return "已识别为格式调整指令，请补充具体参数（如宋体/小四/1.5倍行距）；正文保持不变。"


def should_route_to_revision(
    raw: str,
    text: str,
    analysis: dict | None = None,
    *,
    is_format_only: Callable[[str, dict | None], bool] | None = None,
) -> bool:
    if not str(text or "").strip():
        return False
    compact = re.sub(r"\s+", "", str(raw or ""))
    if not compact:
        return False
    if is_format_only and is_format_only(raw, analysis):
        return False
    if looks_like_modify_instruction(raw):
        return True
    if re.search(r"(生成|撰写|起草|写一份|写一篇|写个|输出|制作|形成)", compact):
        return False
    if isinstance(analysis, dict):
        intent = analysis.get("intent")
        if isinstance(intent, dict):
            name = str(intent.get("name") or "").strip().lower()
            try:
                conf = float(intent.get("confidence") or 0)
            except Exception:
                conf = 0.0
            if name == "modify" and conf >= 0.45:
                return True
            if name == "generate" and conf >= 0.6:
                return False
    return False


def try_handle_format_only_request(
    *,
    session,
    instruction: str,
    base_text: str,
    compose_mode: str,
    selection: str,
    set_doc_text: Callable[[object, str], None],
    save_session: Callable[[object], None],
    safe_doc_ir: Callable[[str], dict],
    apply_format_only_update: Callable[[object, str], str | None],
) -> dict | None:
    if str(selection or "").strip():
        return None
    if compose_mode != "overwrite" and base_text != getattr(session, "doc_text", ""):
        set_doc_text(session, base_text)
    note = apply_format_only_update(session, instruction)
    if note is None:
        return None
    save_session(session)
    final_doc_ir = session.doc_ir if isinstance(getattr(session, "doc_ir", None), dict) else safe_doc_ir(base_text)
    return {
        "text": base_text,
        "problems": [],
        "doc_ir": final_doc_ir,
        "note": note,
        "formatting": getattr(session, "formatting", {}) or {},
        "generation_prefs": getattr(session, "generation_prefs", {}) or {},
    }
