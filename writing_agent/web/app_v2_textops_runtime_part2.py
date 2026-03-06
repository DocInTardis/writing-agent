"""App V2 Textops Runtime Part2 module.

This module belongs to `writing_agent.web` in the writing-agent codebase.
"""

from __future__ import annotations

from functools import wraps

from fastapi import File, Request, UploadFile


_BIND_SKIP_NAMES = {
    "__builtins__",
    "__cached__",
    "__doc__",
    "__file__",
    "__loader__",
    "__name__",
    "__package__",
    "__spec__",
    "_BIND_SKIP_NAMES",
    "_proxy_factory",
    "bind",
    "install",
}


def bind(namespace: dict) -> None:
    for key, value in namespace.items():
        if key in _BIND_SKIP_NAMES:
            continue
        globals()[key] = value


def _proxy_factory(fn_name: str, namespace: dict):
    fn = globals()[fn_name]

    @wraps(fn)
    def _proxy(*args, **kwargs):
        bind(namespace)
        return fn(*args, **kwargs)

    _proxy._wa_runtime_proxy = True
    _proxy._wa_runtime_proxy_target_module = __name__
    _proxy._wa_runtime_proxy_target_name = fn_name
    return _proxy


def install(namespace: dict) -> None:
    bind(namespace)
    for fn_name in EXPORTED_FUNCTIONS:
        namespace[fn_name] = _proxy_factory(fn_name, namespace)

EXPORTED_FUNCTIONS = [
    "_extract_required_sections_from_instruction",
    "_enforce_instruction_requirements",
    "_maybe_convert_json_doc",
    "_normalize_export_text",
    "_clean_export_text",
    "_compact_list_spacing_for_export",
    "_normalize_heading_text",
    "_split_lines",
    "_extract_sections",
    "_contains_cjk",
    "_contains_latin",
    "_preferred_heading_language_is_chinese",
    "_heading_num_prefix",
    "_strip_cross_language_parenthetical",
    "_heading_alias_token",
    "_equivalent_heading_key",
    "_parse_toc_entry_line",
    "_choose_preferred_heading_title",
    "_dedupe_toc_entries",
    "_dedupe_equivalent_headings",
    "_maybe_fix_heading_glue",
    "_fix_section_heading_glue",
    "_normalize_generated_text",
    "_collect_heading_candidates",
    "_extract_heading_candidates_from_text",
    "_heading_candidates_for_revision",
    "_postprocess_output_text",
    "_citation_style_from_session",
    "_strict_doc_format_enabled",
    "_strict_citation_verify_enabled",
    "_allow_possible_citation_status",
    "_instruction_requirement_enforcement_enabled",
    "_has_toc_heading",
    "_has_reference_heading",
    "_collect_toc_titles",
    "_ensure_toc_section",
    "_reference_lines_from_session",
    "_ensure_reference_section",
    "_reference_section_last",
    "_move_reference_section_to_end",
    "_extract_citation_keys_from_text",
    "_has_reference_requirement",
    "_citation_export_issues",
    "_export_quality_report",
    "_insert_reference_section",
    "_apply_citations_for_export",
    "_apply_citations_to_doc_ir",
    "_normalize_doc_ir_for_export",
    "_safe_doc_text",
    "_validate_docx_bytes",
    "_set_doc_text",
    "_safe_doc_ir_payload",
    "_fallback_sections_from_session",
    "_fallback_reference_items",
    "_build_fallback_text",
    "_augment_instruction",
    "_doc_ir_has_styles",
    "api_version_commit",
    "_version_kind_from_tags",
    "_version_diff_summary",
    "api_version_log",
    "api_version_tree",
    "api_version_checkout",
    "api_version_branch",
    "api_version_diff",
    "api_version_tag",
    "_get_current_branch",
    "_auto_commit_version",
    "_convert_to_latex",
    "_render_blocks_to_html",
    "_default_title",
    "_extract_title",
]


def _maybe_convert_json_doc(text: str) -> str | None:
    src = str(text or "").strip()
    if not src or not src.startswith("{"):
        return None
    try:
        data = json.loads(src)
    except Exception:
        return None
    return _json_sections_to_text(data)


def _extract_required_sections_from_instruction(instruction: str) -> list[str]:
    inst = str(instruction or "").strip()
    if not inst:
        return []

    out: list[str] = []
    seen: set[str] = set()

    def _push(value: str) -> None:
        title = str(value or "").strip().strip("`'\"[]()<>")
        if not title:
            return
        title = re.sub(r"^(?:the\s+)?(?:section|part)\s+", "", title, flags=re.IGNORECASE).strip()
        title = re.sub(r"\s+(?:section|part)s?$", "", title, flags=re.IGNORECASE).strip()
        title = title.strip(" .;:,")
        if not title or len(title) < 2:
            return
        token = _normalize_heading_text(title)
        if not token or token in seen:
            return
        seen.add(token)
        out.append(title)

    def _split_and_push(raw: str) -> None:
        text_value = str(raw or "").strip()
        if not text_value:
            return
        for piece in re.split(r"\s*(?:,|;|/|\\|\band\b|&|、|，|；|和|及)\s*", text_value, flags=re.IGNORECASE):
            candidate = str(piece or "").strip()
            if not candidate:
                continue
            if len(candidate) > 64:
                continue
            _push(candidate)

    lower_inst = inst.lower()
    for keyword, heading in [
        ("terminology mapping", "Terminology Mapping"),
        ("editable checklist", "Editable Checklist"),
        ("style guide", "Style Guide"),
        ("draft body", "Draft Body"),
    ]:
        if keyword in lower_inst:
            _push(heading)

    for match in re.finditer(
        r"\b(?:output|include|provide)\b[^:\n]{0,72}\b(?:parts?|sections?)\b\s*:\s*([^\n\.]{2,200})",
        inst,
        flags=re.IGNORECASE,
    ):
        _split_and_push(str(match.group(1) or ""))

    for match in re.finditer(
        r"\b(?:add|include|create|start with|use)\b[^.\n]{0,32}?\b([A-Za-z][A-Za-z0-9 \-/]{2,64}?)\s+section\b",
        inst,
        flags=re.IGNORECASE,
    ):
        _push(str(match.group(1) or ""))

    for match in re.finditer(
        r"(?:必须包含以下一级章节|必须包含以下章节|包含以下一级章节|包含以下章节|章节包括)[:：]\s*([^\n。；;]{2,200})",
        inst,
    ):
        _split_and_push(str(match.group(1) or ""))

    for match in re.finditer(r"[\"'“”‘’]([^\"'“”‘’\n]{2,80})[\"'“”‘’]", inst):
        _push(str(match.group(1) or ""))

    return out


def _ensure_h2_section_exists(text: str, section_title: str) -> str:
    sections = _extract_sections(text, prefer_levels=(2, 3))
    found = section_edit_ops_domain.find_section(
        sections,
        section_title,
        normalize_heading_text=_normalize_heading_text,
    )
    if found is not None:
        return text
    return section_edit_ops_domain.apply_add_section_op(
        text,
        section_title,
        level=2,
        normalize_heading_text=_normalize_heading_text,
    )


def _insert_lines_into_section(text: str, section_title: str, extra_lines: list[str]) -> str:
    out = _ensure_h2_section_exists(str(text or ""), section_title)
    rows = [str(row or "").rstrip() for row in list(extra_lines or []) if str(row or "").strip()]
    if not rows:
        return out
    lines = _split_lines(out)
    sections = _extract_sections(out, prefer_levels=(2, 3))
    sec = section_edit_ops_domain.find_section(
        sections,
        section_title,
        normalize_heading_text=_normalize_heading_text,
    )
    if sec is None:
        return out
    insert_idx = int(getattr(sec, "end", len(lines)) or len(lines))
    block = list(rows)
    if insert_idx > 0 and insert_idx <= len(lines) and lines[insert_idx - 1].strip():
        block = [""] + block
    if block and block[-1].strip():
        block.append("")
    lines[insert_idx:insert_idx] = block
    return "\n".join(lines).strip()


def _append_new_h2_section(text: str, section_title: str, body_lines: list[str]) -> str:
    out = _ensure_h2_section_exists(text, section_title)
    clean_lines = []
    for row in list(body_lines or []):
        line = str(row or "").strip()
        if not line:
            continue
        if re.match(r"^-\s*TODO\b", line, flags=re.IGNORECASE):
            continue
        clean_lines.append(line)
    return _insert_lines_into_section(out, section_title, clean_lines)


def _enforce_instruction_requirements(text: str, instruction: str) -> str:
    return instruction_requirements_domain.enforce_instruction_requirements(
        text,
        instruction,
        extract_required_sections_from_instruction=_extract_required_sections_from_instruction,
        extract_sections=_extract_sections,
        normalize_heading_text=_normalize_heading_text,
        append_new_h2_section=_append_new_h2_section,
        find_section=lambda sections, title: section_edit_ops_domain.find_section(
            sections,
            title,
            normalize_heading_text=_normalize_heading_text,
        ),
        split_lines=_split_lines,
        insert_lines_into_section=_insert_lines_into_section,
    )

def _normalize_export_text(text: str, session=None) -> str:
    s = _clean_export_text(text)
    if _strict_doc_format_enabled(session):
        s = _dedupe_equivalent_headings(s)
    return s.strip()

def _clean_export_text(text: str) -> str:
    return export_quality_domain.clean_export_text(text, json_converter=_maybe_convert_json_doc)

def _compact_list_spacing_for_export(text: str) -> str:
    return export_quality_domain.compact_list_spacing_for_export(text)

def _normalize_heading_text(text: str) -> str:
    value = re.sub(r"^#{1,6}\s*", "", str(text or "")).strip()
    value = re.sub(r"^第[一二三四五六七八九十百千万零两0-9]+[章节部分]\s*", "", value)
    value = re.sub(r"^(?:\d+(?:\.\d+){0,3}|[一二三四五六七八九十百千万零两]+)[\.\uFF0E\u3001\)]\s*", "", value)
    return re.sub(r"\s+", "", value)

def _split_lines(text: str) -> list[str]:
    return section_edit_ops_domain.split_lines(text)

def _extract_sections(text: str, *, prefer_levels: tuple[int, ...] = (2, 3)) -> list:
    return section_edit_ops_domain.extract_sections(text, prefer_levels=prefer_levels)

def _contains_cjk(text: str) -> bool:
    return heading_equivalence_domain.contains_cjk(text)

def _contains_latin(text: str) -> bool:
    return heading_equivalence_domain.contains_latin(text)

def _preferred_heading_language_is_chinese(text: str) -> bool:
    return heading_equivalence_domain.preferred_heading_language_is_chinese(text)

def _heading_num_prefix(title: str) -> tuple[str, str]:
    value = str(title or "").strip()
    match = re.match(r"^((?:\d+(?:\.\d+){0,3}|[一二三四五六七八九十百千万零两]+)[\.\uFF0E\u3001\)]?)\s*(.+)$", value)
    if not match:
        return "", value
    return str(match.group(1) or "").strip(), str(match.group(2) or "").strip()

def _strip_cross_language_parenthetical(title: str, *, prefer_chinese: bool) -> str:
    return heading_equivalence_domain.strip_cross_language_parenthetical(title, prefer_chinese=prefer_chinese)

def _heading_alias_token(text: str) -> str:
    return heading_equivalence_domain.heading_alias_token(
        text,
        normalize_heading_text=_normalize_heading_text,
    )

def _equivalent_heading_key(title: str) -> str:
    return heading_equivalence_domain.equivalent_heading_key(
        title,
        normalize_heading_text=_normalize_heading_text,
        aliases=_HEADING_EQUIV_ALIASES,
    )

def _parse_toc_entry_line(line: str) -> dict | None:
    return heading_equivalence_domain.parse_toc_entry_line(line)

def _choose_preferred_heading_title(candidates: list[str], *, prefer_chinese: bool) -> str:
    return heading_equivalence_domain.choose_preferred_heading_title(
        candidates,
        prefer_chinese=prefer_chinese,
    )

def _dedupe_toc_entries(text: str, *, prefer_chinese: bool) -> str:
    return heading_equivalence_domain.dedupe_toc_entries(
        text,
        prefer_chinese=prefer_chinese,
        split_lines=_split_lines,
        extract_sections=lambda value: _extract_sections(value, prefer_levels=(2, 3)),
        equivalent_heading_key=_equivalent_heading_key,
    )

def _dedupe_equivalent_headings(text: str) -> str:
    return heading_equivalence_domain.dedupe_equivalent_headings(
        text,
        split_lines=_split_lines,
        heading_num_prefix=_heading_num_prefix,
        equivalent_heading_key=_equivalent_heading_key,
        prefer_heading_language_is_chinese=_preferred_heading_language_is_chinese,
        choose_preferred_heading_title=lambda candidates, prefer_chinese: _choose_preferred_heading_title(
            candidates,
            prefer_chinese=prefer_chinese,
        ),
        dedupe_toc_entries=lambda merged, prefer_chinese: _dedupe_toc_entries(
            merged,
            prefer_chinese=prefer_chinese,
        ),
    )

def _maybe_fix_heading_glue(text: str, titles: list[str]) -> str:
    return heading_glue_domain.maybe_fix_heading_glue(
        text,
        titles,
        split_heading_glue=_split_heading_glue_v2,
    )

def _fix_section_heading_glue(text: str, titles: list[str]) -> str:
    return heading_glue_domain.fix_section_heading_glue(
        text,
        titles,
        split_heading_glue=_split_heading_glue_v2,
    )

def _normalize_generated_text(text: str, instruction: str, current_text: str) -> str:
    s = str(text or "").strip()
    if not s:
        return s
    converted = _maybe_convert_json_doc(s)
    if converted:
        s = converted
    # Normalize heading markers like "##Title" -> "## Title".
    s = re.sub(r"(?m)^(#{1,6})([^#\s])", r"\1 \2", s)
    if not re.search(r"(?m)^#\s+", s):
        title = _plan_title(current_text=current_text or s, instruction=instruction)
        if not title:
            title = _extract_title(s)
        s = f"# {title}\n\n" + s.lstrip()
    return s.strip()


def _title_from_instruction(instruction: str) -> str:
    src = str(instruction or "").strip()
    if not src:
        return ""

    m = re.search(r"[《\"“](.{4,80}?)[》\"”]", src)
    if m:
        return str(m.group(1) or "").strip()

    m = re.search(r"(?:题目|标题)\s*[:：]\s*([^\n。；;]{4,80})", src, flags=re.IGNORECASE)
    if m:
        return str(m.group(1) or "").strip().strip("`'\"")

    return ""


def _looks_like_promptish_title(title: str) -> bool:
    t = str(title or "").strip()
    if not t:
        return True
    if len(t) < 6:
        return True
    low = t.lower()
    bad_patterns = [
        r"^(请|帮我|给我|麻烦).{0,20}(写|生成|输出|做)",
        r"^(写一篇|写一个|生成一篇|生成一个|输出一篇|输出一个)",
        r"^请写一篇(?:本科|硕士|博士)?(?:毕业设计|毕业论文|技术报告)?",
        r"^(技术报告|报告|文档|文章)$",
        r"(技术报告|毕业设计).{0,8}(模板|示例|演示)$",
    ]
    for pat in bad_patterns:
        if re.search(pat, t, flags=re.IGNORECASE):
            return True
    if "请写" in t or "帮我" in t or "给我" in t:
        return True
    if low.startswith("generate ") or low.startswith("write "):
        return True
    return False


def _replace_h1_title(text: str, new_title: str) -> str:
    title = str(new_title or "").strip()
    if not title:
        return str(text or "").strip()
    lines = _split_lines(str(text or ""))
    for idx, line in enumerate(lines):
        if re.match(r"^#\s+.+$", str(line or "").strip()):
            lines[idx] = f"# {title}"
            return "\n".join(lines).strip()
    return f"# {title}\n\n{str(text or '').strip()}".strip()


def _sanitize_reference_item(item: str) -> str:
    value = re.sub(r"\s+", " ", str(item or "").strip())
    if not value:
        return ""

    value = re.sub(r"以上内容[^。；;]*?(?:字|字符)[^。；;]*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"字数[^。；;]*?(?:要求|范围)[^。；;]*", "", value, flags=re.IGNORECASE)

    # Canonicalize common DOI URL spacing issues, e.g. "https://doi.org/ 10.1000/xyz".
    value = re.sub(r"https?://doi\.org/\s+", "https://doi.org/", value, flags=re.IGNORECASE)
    m = re.search(r"(https?://doi\.org/)(.+)$", value, flags=re.IGNORECASE)
    if m:
        doi_tail = re.sub(r"\s+", "", str(m.group(2) or "").strip())
        value = value[: m.start(2)] + doi_tail
    return value.strip(" ;，。")


def _looks_like_doi_fragment(item: str) -> bool:
    value = str(item or "").strip().lower()
    if not value:
        return False
    if value.startswith("10.") and "/" in value:
        return True
    if value.startswith("0.") and "/" in value:
        return True
    return False


def _looks_like_incomplete_doi_link(item: str) -> bool:
    value = str(item or "").strip()
    m = re.search(r"https?://doi\.org/(\S*)", value, flags=re.IGNORECASE)
    if not m:
        return False
    tail = str(m.group(1) or "").strip()
    if not tail:
        return True
    tail_compact = re.sub(r"[^0-9A-Za-z./_-]+", "", tail)
    if len(tail_compact) <= 5:
        return True
    if "/" not in tail_compact:
        return True
    return False


def _reference_conservative_repair_enabled() -> bool:
    raw = str(os.environ.get("WRITING_AGENT_REFERENCE_CONSERVATIVE_REPAIR", "1")).strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _reference_section_bounds(text: str) -> tuple[int, int, list[str]]:
    lines = _split_lines(str(text or ""))
    start = -1
    for idx, line in enumerate(lines):
        row = str(line or "").strip()
        if re.match(r"^#{2,3}\s*(参考文献|references?)\s*$", row, flags=re.IGNORECASE):
            start = idx
            break
        if re.match(r"^(参考文献|references?)\s*$", row, flags=re.IGNORECASE):
            start = idx
            break
    if start < 0:
        return -1, -1, lines

    end = len(lines)
    for idx in range(start + 1, len(lines)):
        if re.match(r"^#{1,3}\s+.+$", str(lines[idx] or "").strip()):
            end = idx
            break
    return start, end, lines


def _extract_reference_items_from_text(text: str) -> list[str]:
    start, end, lines = _reference_section_bounds(text)
    if start < 0:
        return []
    body = lines[start + 1 : end]
    items: list[str] = []
    cur = ""

    def _flush() -> None:
        nonlocal cur
        if cur.strip():
            items.append(cur.strip())
        cur = ""

    for raw in body:
        row = str(raw or "").strip()
        if not row:
            continue
        row = row.replace("↵", "").strip()
        m_num = re.match(r"^\[(\d+)\]\s*(.+)$", row)
        if m_num:
            content = str(m_num.group(2) or "").strip()
            _flush()
            cur = content
            continue
        if cur:
            cur = (cur + " " + row).strip()
        elif items:
            items[-1] = (items[-1] + " " + row).strip()
        else:
            cur = row
    _flush()

    merged: list[str] = []
    for raw_item in items:
        item = _sanitize_reference_item(raw_item)
        if not item:
            continue
        if merged and _looks_like_doi_fragment(item) and _looks_like_incomplete_doi_link(merged[-1]):
            merged[-1] = _sanitize_reference_item(merged[-1] + item)
            continue
        merged.append(item)
    conservative = _reference_conservative_repair_enabled()
    if conservative:
        deduped: list[str] = []
        seen: set[str] = set()
        for item in merged:
            clean = _sanitize_reference_item(item)
            norm = re.sub(r"\s+", " ", clean).strip().lower()
            if not norm or norm in seen:
                continue
            seen.add(norm)
            deduped.append(clean)
        return deduped

    def _split_compound_reference_item(item: str) -> list[str]:
        src = str(item or "").strip()
        if not src:
            return []
        if not re.match(r"^\d+\.\s+", src):
            return [src]
        pieces = [str(x or "").strip() for x in re.split(r"\s+(?=\d+\.\s+)", src) if str(x or "").strip()]
        out: list[str] = []
        for piece in pieces:
            value = re.sub(r"^\d+\.\s*", "", piece).strip()
            if value:
                out.append(value)
        return out or [src]

    deduped: list[str] = []
    seen: set[str] = set()
    for item in merged:
        for piece in _split_compound_reference_item(item):
            clean = _sanitize_reference_item(piece)
            norm = re.sub(r"\s+", " ", clean).strip().lower()
            if not norm or norm in seen:
                continue
            seen.add(norm)
            deduped.append(clean)
    return deduped


def _topic_reference_seeds(instruction: str, text: str) -> list[str]:
    q = f"{instruction}\n{text}".lower()
    if any(k in q for k in ("rag", "retrieval", "检索增强", "向量检索", "语义检索")):
        return [
            "Lewis P, Perez E, Piktus A, et al. Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks. 2020. URL: https://arxiv.org/abs/2005.11401",
            "Izacard G, Grave E. Leveraging Passage Retrieval with Generative Models for Open Domain Question Answering. 2021. URL: https://arxiv.org/abs/2007.01282",
            "OpenAI. Structured Outputs Guide. 2024. URL: https://platform.openai.com/docs/guides/structured-outputs",
        ]
    if any(k in q for k in ("微服务", "microservice", "service mesh", "kubernetes")):
        return [
            "Newman S. Building Microservices: Designing Fine-Grained Systems. 2021. URL: https://www.oreilly.com/library/view/building-microservices-2nd/9781492034018/",
            "Burns B, Beda J, Hightower K. Kubernetes: Up and Running. 2022. URL: https://www.oreilly.com/library/view/kubernetes-up-and/9781098110192/",
            "NGINX. Microservices Reference Architecture. 2023. URL: https://www.nginx.com/blog/introduction-to-microservices/",
        ]
    if any(k in q for k in ("排版", "格式", "docx", "word", "导出")):
        return [
            "IETF. RFC 5789: PATCH Method for HTTP. 2010. URL: https://www.rfc-editor.org/rfc/rfc5789",
            "IETF. RFC 6902: JavaScript Object Notation (JSON) Patch. 2013. URL: https://www.rfc-editor.org/rfc/rfc6902",
            "Ecma International. ECMA-376 Office Open XML File Formats. 2021. URL: https://ecma-international.org/publications-and-standards/standards/ecma-376/",
        ]
    return [
        "OpenAI. Structured Outputs Guide. 2024. URL: https://platform.openai.com/docs/guides/structured-outputs",
        "IETF. RFC 5789: PATCH Method for HTTP. 2010. URL: https://www.rfc-editor.org/rfc/rfc5789",
        "IETF. RFC 6902: JavaScript Object Notation (JSON) Patch. 2013. URL: https://www.rfc-editor.org/rfc/rfc6902",
    ]


def _normalize_primary_title(text: str, instruction: str) -> str:
    src = str(text or "").strip()
    if not src:
        return src
    inferred = _title_from_instruction(instruction)
    lines = _split_lines(src)
    current_h1 = ""
    for line in lines:
        m = re.match(r"^#\s+(.+)$", str(line or "").strip())
        if m:
            current_h1 = str(m.group(1) or "").strip()
            break
    if current_h1 and not _looks_like_promptish_title(current_h1):
        return src

    if inferred:
        return _replace_h1_title(src, inferred)

    if current_h1 and not _looks_like_promptish_title(current_h1):
        return src

    fallback = _extract_title(src)
    if _looks_like_promptish_title(fallback):
        fallback = _default_title()
    return _replace_h1_title(src, fallback)


def _repair_reference_section_lines(text: str) -> str:
    src = str(text or "").strip()
    if not src:
        return src
    start, end, lines = _reference_section_bounds(src)
    if start < 0:
        return src
    deduped = _extract_reference_items_from_text(src)

    if not deduped:
        return src

    rebuilt = [f"[{idx}] {content}" for idx, content in enumerate(deduped, start=1)]
    new_lines = list(lines[: start + 1]) + [""] + rebuilt + [""] + list(lines[end:])
    return "\n".join(new_lines).strip()


def _compact_char_len(text: str) -> int:
    return len(re.sub(r"\s+", "", str(text or "")))


def _is_longform_academic_intent(instruction: str, text: str, session=None) -> bool:
    prefs = (getattr(session, "generation_prefs", {}) or {}) if session is not None else {}
    try:
        target_chars = int(prefs.get("target_char_count") or 0)
    except Exception:
        target_chars = 0
    if target_chars >= 2200:
        return True
    joined = f"{instruction}\n{text}".lower()
    return any(k in joined for k in ("论文", "毕业设计", "技术报告", "学术", "研究", "thesis", "report"))


def _resolve_min_chars(session, instruction: str, text: str) -> int:
    prefs = (getattr(session, "generation_prefs", {}) or {}) if session is not None else {}
    try:
        target_chars = int(prefs.get("target_char_count") or 0)
    except Exception:
        target_chars = 0
    if target_chars > 0:
        return max(1200, min(9000, int(target_chars * 0.82)))
    if _is_longform_academic_intent(instruction, text, session=session):
        return 2800
    return 320


def _strip_chatty_tail(text: str) -> str:
    src = str(text or "").strip()
    if not src:
        return src
    lines = _split_lines(src)
    bad_markers = [
        "希望这个方案",
        "希望能对你有所帮助",
        "如果有任何问题",
        "请随时告诉我",
        "祝你",
        "可以根据实际情况进行调整",
        "以上是关于",
    ]
    cut = len(lines)
    for idx, raw in enumerate(lines):
        row = str(raw or "").strip()
        if not row:
            continue
        if any(marker in row for marker in bad_markers):
            if idx >= max(0, len(lines) - 12) or row.startswith("以上是关于"):
                cut = min(cut, idx)
                break
    if cut < len(lines):
        return "\n".join(lines[:cut]).strip()
    return src


def _ensure_practical_min_length(text: str, instruction: str, *, min_chars: int = 280, session=None) -> str:
    src = str(text or "").strip()
    if not src:
        return src
    needed = max(120, int(min_chars or 280))
    if _compact_char_len(src) >= needed:
        return src

    if not _is_longform_academic_intent(instruction, src, session=session):
        return src

    out = src
    if not out.endswith("\n"):
        out += "\n"
    if "## 工程化细节与复现实验" not in out:
        out += "\n## 工程化细节与复现实验\n"
    seed_lines = [
        "为提升可复现性，实验应固定随机种子、模型版本、推理温度与检索参数，并在附录中给出完整配置清单，以保证不同环境下结果可比。",
        "系统评测建议同时覆盖功能正确性、时延稳定性、异常恢复与导出一致性，并对失败样本进行误差归因，避免仅以单一平均指标判断效果。",
        "在工程落地阶段，应建立从输入约束、过程校验到导出验收的闭环流程，通过自动化检查降低格式漂移、引用断裂与标题异常对最终文档质量的影响。",
        "对于关键章节，建议引入可解释证据链，包括来源标注、参数记录与版本追踪，以便在答辩或复审阶段快速定位结论依据并完成技术复核。",
    ]
    idx = 0
    while _compact_char_len(out) < needed and idx < 32:
        out += seed_lines[idx % len(seed_lines)] + "\n\n"
        idx += 1
    return out.strip()


def _upsert_reference_section(text: str, items: list[str]) -> str:
    src = str(text or "").strip()
    clean_items = [str(x or "").strip() for x in list(items or []) if str(x or "").strip()]
    if not clean_items:
        return src
    numbered = [f"[{idx}] {item}" for idx, item in enumerate(clean_items, start=1)]
    start, end, lines = _reference_section_bounds(src)
    if start < 0:
        out = src.rstrip()
        if out and not out.endswith("\n"):
            out += "\n"
        out += "\n## 参考文献\n\n" + "\n".join(numbered) + "\n"
        return out.strip()
    new_lines = list(lines[: start + 1]) + [""] + numbered + [""] + list(lines[end:])
    return "\n".join(new_lines).strip()


def _ensure_reference_section_quality(session, text: str, instruction: str, *, min_unique: int = 6) -> str:
    src = str(text or "").strip()
    if not src:
        return src
    fixed = _repair_reference_section_lines(src)
    items = _extract_reference_items_from_text(fixed)
    target_unique = max(1, int(min_unique))
    prefs = session.generation_prefs if isinstance(getattr(session, "generation_prefs", None), dict) else {}
    try:
        pref_min = int((prefs or {}).get("min_reference_count") or 0)
    except Exception:
        pref_min = 0
    if pref_min > 0:
        target_unique = max(target_unique, pref_min)
    if len(items) >= target_unique:
        return fixed

    merged: list[str] = list(items)
    fallback_lines: list[str] = []
    try:
        fallback_lines = _fallback_reference_items(session, str(instruction or "").strip()) if session is not None else []
    except Exception:
        fallback_lines = []
    for row in fallback_lines:
        value = str(row or "").strip()
        if not value:
            continue
        m = re.match(r"^\[\d+\]\s*(.+)$", value)
        merged.append(str(m.group(1) if m else value).strip())

    deduped: list[str] = []
    seen: set[str] = set()
    for item in merged:
        clean = _sanitize_reference_item(item)
        norm = re.sub(r"\s+", " ", clean).strip().lower()
        if not norm or norm in seen:
            continue
        seen.add(norm)
        deduped.append(clean)
    if len(deduped) < target_unique:
        return fixed
    return _upsert_reference_section(fixed, deduped)

def _collect_heading_candidates(session) -> list[str]:
    return heading_candidates_domain.collect_heading_candidates(session, _FAST_REPORT_SECTIONS)

def _extract_heading_candidates_from_text(text: str) -> list[str]:
    return heading_candidates_domain.extract_heading_candidates_from_text(
        text,
        parse_report_text=parse_report_text,
    )

def _heading_candidates_for_revision(session, base_text: str) -> list[str]:
    return heading_candidates_domain.heading_candidates_for_revision(
        session,
        base_text,
        fast_report_sections=_FAST_REPORT_SECTIONS,
        parse_report_text=parse_report_text,
    )

def _postprocess_output_text(
    session,
    text: str,
    instruction: str,
    *,
    current_text: str,
    base_text: str | None = None,
) -> str:
    s = _sanitize_output_text(text)
    base = base_text if base_text is not None else current_text
    s = _normalize_generated_text(s, instruction, current_text or base)
    s = _normalize_primary_title(s, instruction)
    titles = _heading_candidates_for_revision(session, base or "")
    if titles:
        s = _fix_section_heading_glue(s, titles)
    s = _strip_chatty_tail(s)
    if _instruction_requirement_enforcement_enabled():
        s = _enforce_instruction_requirements(s, instruction)
    min_chars = _resolve_min_chars(session, instruction, s)
    s = _ensure_practical_min_length(s, instruction, min_chars=min_chars, session=session)
    s = _ensure_reference_section_quality(session, s, instruction, min_unique=6)
    s = _repair_reference_section_lines(s)
    return s

def _citation_style_from_session(session) -> CitationStyle:
    raw = str((session.formatting or {}).get("citation_style") or "").strip()
    if not raw:
        return CitationStyle.GBT
    key = raw.replace(" ", "").replace("-", "").replace("_", "").upper()
    if key in {"APA"}:
        return CitationStyle.APA
    if key in {"IEEE"}:
        return CitationStyle.IEEE
    if key in {"GBT", "GB", "GBT7714", "GB/T", "GB/T7714"}:
        return CitationStyle.GBT
    return CitationStyle.GBT

def _strict_doc_format_enabled(session) -> bool:
    prefs = session.generation_prefs if isinstance(getattr(session, "generation_prefs", None), dict) else {}
    pref_value = export_quality_domain.coerce_optional_bool((prefs or {}).get("strict_doc_format"))
    if pref_value is not None:
        return pref_value
    env_value = export_quality_domain.coerce_optional_bool(
        os.environ.get("WRITING_AGENT_STRICT_DOC_FORMAT_DEFAULT", "0")
    )
    return bool(env_value)

def _strict_citation_verify_enabled(session) -> bool:
    prefs = session.generation_prefs if isinstance(getattr(session, "generation_prefs", None), dict) else {}
    pref_value = export_quality_domain.coerce_optional_bool((prefs or {}).get("strict_citation_verify"))
    if pref_value is not None:
        return pref_value
    profile = str((prefs or {}).get("quality_profile") or "").strip().lower()
    if profile == "academic_cnki_default":
        return True
    env_value = export_quality_domain.coerce_optional_bool(
        os.environ.get("WRITING_AGENT_STRICT_CITATION_VERIFY_DEFAULT", "0")
    )
    return bool(env_value)

def _allow_possible_citation_status(session) -> bool:
    prefs = session.generation_prefs if isinstance(session.generation_prefs, dict) else {}
    raw = str((prefs or {}).get("allow_possible_citation") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}

def _instruction_requirement_enforcement_enabled() -> bool:
    raw = str(os.environ.get("WRITING_AGENT_ENFORCE_INSTRUCTION_REQUIREMENTS", "0")).strip().lower()
    return raw in {"1", "true", "yes", "on"}

def _has_toc_heading(text: str) -> bool:
    return export_structure_domain.has_toc_heading(text)

def _has_reference_heading(text: str) -> bool:
    return export_structure_domain.has_reference_heading(text)

def _collect_toc_titles(text: str) -> list[str]:
    return export_structure_domain.collect_toc_titles(
        text,
        extract_sections=_extract_sections,
        is_reference_section=_is_reference_section,
    )

def _ensure_toc_section(text: str) -> str:
    return export_structure_domain.ensure_toc_section(
        text,
        extract_sections=_extract_sections,
        is_reference_section=_is_reference_section,
        split_lines=_split_lines,
    )

def _reference_lines_from_session(session) -> list[str]:
    citer = CitationAgent()
    return export_structure_domain.reference_lines_from_session(
        session,
        citation_style_from_session=_citation_style_from_session,
        format_reference=lambda cite, style: citer.format_reference(cite, style),
    )

def _ensure_reference_section(text: str, session) -> str:
    return export_structure_domain.ensure_reference_section(
        text,
        session,
        has_reference_heading_fn=_has_reference_heading,
        reference_lines_from_session_fn=_reference_lines_from_session,
        insert_reference_section=_insert_reference_section,
    )

def _reference_section_last(text: str) -> bool:
    return export_structure_domain.reference_section_last(
        text,
        extract_sections=_extract_sections,
        is_reference_section=_is_reference_section,
    )

def _move_reference_section_to_end(text: str) -> str:
    return export_structure_domain.move_reference_section_to_end(
        text,
        extract_sections=_extract_sections,
        is_reference_section=_is_reference_section,
        apply_move_section_op=lambda value, title, anchor, position="after": section_edit_ops_domain.apply_move_section_op(
            value,
            title,
            anchor,
            position=position,
            normalize_heading_text=_normalize_heading_text,
        ),
    )

def _extract_citation_keys_from_text(text: str) -> list[str]:
    return export_structure_domain.extract_citation_keys_from_text(text)

def _has_reference_requirement(session, text: str) -> bool:
    return export_structure_domain.has_reference_requirement(
        session,
        text,
        has_reference_heading_fn=_has_reference_heading,
        reference_lines_from_session_fn=_reference_lines_from_session,
    )

def _citation_export_issues(session, text: str) -> list[dict]:
    return export_structure_domain.citation_export_issues(
        session,
        text,
        strict_citation_verify_enabled=_strict_citation_verify_enabled,
        get_internal_pref=_get_internal_pref,
        citation_verify_key=_CITATION_VERIFY_KEY,
        allow_possible_citation_status=_allow_possible_citation_status,
    )

def _export_quality_report(session, text: str, *, auto_fix: bool = False) -> dict:
    return export_structure_domain.export_quality_report(
        session,
        text,
        auto_fix=auto_fix,
        export_gate_policy=_export_gate_policy,
        strict_doc_format_enabled=_strict_doc_format_enabled,
        has_reference_requirement_fn=_has_reference_requirement,
        normalize_export_text=_normalize_export_text,
        ensure_toc_section_fn=_ensure_toc_section,
        ensure_reference_section_fn=_ensure_reference_section,
        move_reference_section_to_end_fn=_move_reference_section_to_end,
        has_toc_heading_fn=_has_toc_heading,
        has_reference_heading_fn=_has_reference_heading,
        reference_section_last_fn=_reference_section_last,
        citation_export_issues_fn=_citation_export_issues,
    )

def _insert_reference_section(text: str, ref_lines: list[str]) -> str:
    return citation_render_domain.insert_reference_section(text, ref_lines)

def _apply_citations_for_export(text: str, citations: dict[str, Citation], style: CitationStyle) -> str:
    return citation_render_domain.apply_citations_for_export(text, citations, style)

def _apply_citations_to_doc_ir(doc_ir, citations: dict[str, Citation], style: CitationStyle):
    return citation_render_domain.apply_citations_to_doc_ir(doc_ir, citations, style)

def _normalize_doc_ir_for_export(doc_ir, session):
    return doc_state_domain.normalize_doc_ir_for_export(
        doc_ir,
        session,
        ensure_mcp_citations=_ensure_mcp_citations,
        doc_ir_from_dict=doc_ir_from_dict,
        doc_ir_to_text=doc_ir_to_text,
        doc_ir_from_text=doc_ir_from_text,
        doc_ir_has_styles=_doc_ir_has_styles,
        normalize_export_text=_normalize_export_text,
    )

def _safe_doc_text(session) -> str:
    return doc_state_domain.safe_doc_text(
        session,
        plan_title=_plan_title,
        fallback_sections_from_session=_fallback_sections_from_session,
        build_fallback_text=_build_fallback_text,
        store_put=store.put,
        doc_ir_to_text=doc_ir_to_text,
        doc_ir_from_dict=doc_ir_from_dict,
        set_doc_text=_set_doc_text,
    )

def _validate_docx_bytes(docx_bytes: bytes) -> list[str]:
    return doc_state_domain.validate_docx_bytes(docx_bytes)

def _set_doc_text(session, text: str) -> None:
    return doc_state_domain.set_doc_text(
        session,
        text,
        doc_ir_to_dict=doc_ir_to_dict,
        doc_ir_from_text=doc_ir_from_text,
    )

def _safe_doc_ir_payload(text: str) -> dict:
    return doc_state_domain.safe_doc_ir_payload(
        text,
        doc_ir_to_dict=doc_ir_to_dict,
        doc_ir_from_text=doc_ir_from_text,
    )

def _fallback_sections_from_session(session) -> list[str]:
    return fallback_content_domain.fallback_sections_from_session(
        session,
        default_sections=["引言", "需求分析", "总体设计", "数据库设计", "测试与结果", "结论", "参考文献"],
    )

def _fallback_reference_items(session, query: str) -> list[str]:
    return fallback_content_domain.fallback_reference_items(
        session,
        query,
        rag_list_papers=rag_store.list_papers,
        search_papers=search_papers,
        format_reference_items=_format_reference_items,
    )

def _build_fallback_text(title: str, sections: list[str], session=None) -> str:
    return fallback_content_domain.build_fallback_text(
        title,
        sections,
        session,
        is_reference_section=_is_reference_section,
        generic_fill_paragraph=_generic_fill_paragraph,
        merge_sections_text=_merge_sections_text,
        default_title=_default_title,
        fallback_reference_items_fn=_fallback_reference_items,
    )

def _augment_instruction(instruction: str, *, formatting: dict, generation_prefs: dict) -> str:
    return fallback_content_domain.augment_instruction(
        instruction,
        formatting=formatting,
        generation_prefs=generation_prefs,
    )

def _doc_ir_has_styles(doc_ir) -> bool:
    return doc_state_domain.doc_ir_has_styles(doc_ir, doc_ir_to_dict=doc_ir_to_dict)

async def api_version_commit(doc_id: str, request: Request) -> dict:
    from writing_agent.web.api.version_flow import version_commit

    return await version_commit(doc_id, request)

def _version_kind_from_tags(tags) -> str:
    return version_state_domain.version_kind_from_tags(tags)

def _version_diff_summary(prev_doc_ir: dict, next_doc_ir: dict) -> dict:
    return version_state_domain.version_diff_summary(
        prev_doc_ir,
        next_doc_ir,
        doc_ir_from_dict=doc_ir_from_dict,
        doc_ir_diff=doc_ir_diff,
    )

def api_version_log(doc_id: str, branch: str = "main", limit: int = 50) -> dict:
    from writing_agent.web.api.version_flow import version_log

    return version_log(doc_id, branch=branch, limit=limit)

def api_version_tree(doc_id: str) -> dict:
    from writing_agent.web.api.version_flow import version_tree

    return version_tree(doc_id)

async def api_version_checkout(doc_id: str, request: Request) -> dict:
    from writing_agent.web.api.version_flow import version_checkout

    return await version_checkout(doc_id, request)

async def api_version_branch(doc_id: str, request: Request) -> dict:
    from writing_agent.web.api.version_flow import version_branch

    return await version_branch(doc_id, request)

def api_version_diff(doc_id: str, from_version: str, to_version: str) -> dict:
    from writing_agent.web.api.version_flow import version_diff

    return version_diff(doc_id, from_version=from_version, to_version=to_version)

async def api_version_tag(doc_id: str, request: Request) -> dict:
    from writing_agent.web.api.version_flow import version_tag

    return await version_tag(doc_id, request)

def _get_current_branch(session) -> str:
    return version_state_domain.get_current_branch(session)

def _auto_commit_version(session, message: str, *, author: str = "system", tags: list[str] | None = None) -> str | None:
    return version_state_domain.auto_commit_version(
        session,
        message,
        author=author,
        tags=tags,
        get_current_branch_fn=_get_current_branch,
        version_node_cls=VersionNode,
        version_id_factory=lambda: uuid.uuid4().hex[:12],
        now_ts=time.time,
    )

def _convert_to_latex(text: str, title: str) -> str:
    return _convert_to_latex_base(text, title)

def _render_blocks_to_html(blocks) -> str:
    return _render_blocks_to_html_base(blocks)

def _default_title() -> str:
    return _default_title_base()

def _extract_title(text: str) -> str:
    return _extract_title_base(text)
