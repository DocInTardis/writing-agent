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
    "_esc",
    "_doc_ir_has_styles",
    "_style_dict_to_css",
    "_run_to_html",
    "_runs_to_html",
    "_doc_ir_to_html",
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
    inst = str(instruction or "")
    if not inst:
        return []
    out: list[str] = []
    seen: set[str] = set()

    def _push(value: str) -> None:
        title = str(value or "").strip().strip("“”\"'`[]()（）")
        title = re.sub(r"^(?:第[一二三四五六七八九十0-9]+(?:部分|章|节)\s*[“\"]?)", "", title).strip()
        title = re.sub(r"(?:等|等等|等章节|等部分)$", "", title).strip("，,。；;:： ")
        if not title or len(title) < 2:
            return
        token = _normalize_heading_text(title)
        if not token or token in seen:
            return
        seen.add(token)
        out.append(title)

    patterns = [
        r"(?:必须|需要|应当|需)\s*包含(?:以下)?(?:一级)?章节\s*[：:]\s*([^\n。；;]+)",
        r"(?:章节包括|包含章节)\s*[：:]\s*([^\n。；;]+)",
    ]
    for pat in patterns:
        for match in re.finditer(pat, inst, flags=re.IGNORECASE):
            raw = str(match.group(1) or "").strip()
            if not raw:
                continue
            for piece in re.split(r"[、,，;；/|]+", raw):
                _push(piece)

    if out:
        return out

    # Fallback: extract quoted section titles in instructions such as “执行版清单”.
    for match in re.finditer(r"[“\"]([^”\"\n]{2,40})[”\"]", inst):
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
    titles = _heading_candidates_for_revision(session, base or "")
    if titles:
        s = _fix_section_heading_glue(s, titles)
    if _instruction_requirement_enforcement_enabled():
        s = _enforce_instruction_requirements(s, instruction)
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

def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

def _doc_ir_has_styles(doc_ir) -> bool:
    return doc_state_domain.doc_ir_has_styles(doc_ir, doc_ir_to_dict=doc_ir_to_dict)

def _style_dict_to_css(style: dict | None) -> str:
    return doc_ir_html_domain.style_dict_to_css(style, esc=_esc)

def _run_to_html(run: dict) -> str:
    return doc_ir_html_domain.run_to_html(run, esc=_esc)

def _runs_to_html(runs: list[dict]) -> str:
    return doc_ir_html_domain.runs_to_html(runs, esc=_esc)

def _doc_ir_to_html(doc_ir) -> str:
    return doc_ir_html_domain.doc_ir_to_html(doc_ir, esc=_esc, doc_ir_to_dict=doc_ir_to_dict)

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
