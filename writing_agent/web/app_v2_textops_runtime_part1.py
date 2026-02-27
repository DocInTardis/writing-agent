"""App V2 Textops Runtime Part1 module.

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
    "_try_quick_edit",
    "_try_ai_intent_edit",
    "_looks_like_modify_instruction",
    "_extract_format_only_updates",
    "_try_format_only_update",
    "_should_route_to_revision",
    "_try_handle_format_only_request",
    "_try_revision_edit",
    "_analysis_timeout_s",
    "_revision_decision_with_model",
    "_extract_timeout_s",
    "_analysis_model_name",
    "_build_analysis_context",
    "_normalize_analysis",
    "_compose_analysis_input",
    "_build_pref_summary",
    "_field_confidence",
    "_low_conf_questions",
    "_prioritize_missing",
    "_build_missing_questions",
    "_length_from_text",
    "_analysis_history_context",
    "_generate_dynamic_questions_with_model",
    "_detect_extract_conflicts",
    "_infer_role_defaults",
    "_detect_multi_intent",
    "_info_score",
    "_run_message_analysis",
    "_classify_upload_with_model",
    "_extract_template_with_model",
    "_extract_template_refine_with_model",
    "_extract_prefs_with_model",
    "_extract_template_titles_with_model",
    "_extract_prefs_refine_with_model",
    "_coerce_float",
    "_coerce_int",
    "_fast_extract_prefs",
    "_normalize_ai_formatting",
    "_replace_question_headings",
    "_normalize_ai_prefs",
    "_formatting_from_session",
    "_export_prefs_from_session",
    "_estimate_chars_per_page",
    "_resolve_target_chars",
    "_extract_target_chars_from_instruction",
    "_json_sections_to_text",
]


def _try_quick_edit(text: str, instruction: str) -> tuple[str, str] | None:
    return revision_edit_runtime_domain.try_quick_edit(
        text,
        instruction,
        looks_like_modify_instruction=_looks_like_modify_instruction,
    )

def _try_ai_intent_edit(text: str, instruction: str, analysis: dict | None = None) -> tuple[str, str] | None:
    return revision_edit_runtime_domain.try_ai_intent_edit(
        text,
        instruction,
        analysis,
        looks_like_modify_instruction=_looks_like_modify_instruction,
    )

def _looks_like_modify_instruction(raw: str) -> bool:
    return _looks_like_modify_instruction_base(raw)

def _extract_format_only_updates(raw: str, analysis: dict | None = None) -> dict | None:
    parsed = _extract_format_only_updates_base(
        raw,
        analysis,
        parse_prefs=_fast_extract_prefs,
        normalize_formatting=_normalize_ai_formatting,
        normalize_prefs=_normalize_ai_prefs,
    )
    text = str(raw or "")
    compact = re.sub(r"\s+", "", text).lower()
    heuristic_fmt: dict[str, object] = {}
    if "宋体" in text or "simsun" in compact:
        heuristic_fmt["font_name_east_asia"] = "宋体"
    elif "黑体" in text or "simhei" in compact:
        heuristic_fmt["font_name_east_asia"] = "黑体"
    if "小四" in text or "12pt" in compact:
        heuristic_fmt["font_size_pt"] = 12
    elif "三号" in text or "16pt" in compact:
        heuristic_fmt["font_size_pt"] = 16
    m_spacing = re.search(r"行距\s*([0-9]+(?:\.[0-9]+)?)\s*倍", text)
    if m_spacing:
        try:
            heuristic_fmt["line_spacing"] = float(m_spacing.group(1))
        except Exception:
            pass
    elif "1.5倍" in compact:
        heuristic_fmt["line_spacing"] = 1.5

    if isinstance(parsed, dict):
        fmt = dict(parsed.get("formatting") or {})
        if heuristic_fmt:
            for key, value in heuristic_fmt.items():
                if key not in fmt or fmt.get(key) in (None, "", 0):
                    fmt[key] = value
        parsed["formatting"] = fmt
        parsed["has_values"] = bool(fmt or (parsed.get("generation_prefs") or {}))
        return parsed

    if heuristic_fmt:
        return {"formatting": heuristic_fmt, "generation_prefs": {}, "has_values": True}
    return parsed

def _try_format_only_update(session, instruction: str, analysis: dict | None = None) -> str | None:
    return _try_format_only_update_base(
        session,
        instruction,
        analysis,
        extract_updates=_extract_format_only_updates,
    )

def _should_route_to_revision(raw: str, text: str, analysis: dict | None = None) -> bool:
    return _should_route_to_revision_base(
        raw,
        text,
        analysis,
        is_format_only=lambda value, state: _extract_format_only_updates(value, state) is not None,
    )

def _try_handle_format_only_request(
    *,
    session,
    instruction: str,
    base_text: str,
    compose_mode: str,
    selection: str,
) -> dict | None:
    return _try_handle_format_only_request_base(
        session=session,
        instruction=instruction,
        base_text=base_text,
        compose_mode=compose_mode,
        selection=selection,
        set_doc_text=_set_doc_text,
        save_session=store.put,
        safe_doc_ir=_safe_doc_ir_payload,
        apply_format_only_update=_try_format_only_update,
    )

def _try_revision_edit(
    *,
    session,
    instruction: str,
    text: str,
    selection: str = "",
    analysis: dict | None = None,
) -> tuple[str, str] | None:
    return revision_edit_runtime_domain.try_revision_edit(
        session=session,
        instruction=instruction,
        text=text,
        selection=selection,
        analysis=analysis,
        sanitize_output_text=_sanitize_output_text,
        replace_question_headings=_replace_question_headings,
        get_ollama_settings_fn=get_ollama_settings,
        ollama_client_cls=OllamaClient,
    )

def _analysis_timeout_s() -> float:
    raw = os.environ.get("WRITING_AGENT_ANALYSIS_TIMEOUT_S", "").strip()
    if raw:
        try:
            return max(2.0, float(raw))
        except Exception:
            pass
    return 45.0

def _revision_decision_with_model(
    *,
    base_url: str,
    model: str,
    instruction: str,
    selection: str,
    text: str,
) -> dict:
    # Conservative fallback during refactor: prefer applying revision path.
    return {"should_apply": True, "reason": "fallback", "plan": []}

def _extract_timeout_s() -> float:
    raw = os.environ.get("WRITING_AGENT_EXTRACT_TIMEOUT_S", "").strip()
    if raw:
        try:
            return max(4.0, float(raw))
        except Exception:
            pass
    return 20.0

def _analysis_model_name(settings) -> str:
    cand = os.environ.get("WRITING_AGENT_ANALYSIS_MODEL", "").strip()
    if cand:
        return cand
    cand = os.environ.get("WRITING_AGENT_AGG_MODEL", "").strip()
    if cand:
        return cand
    return settings.model

def _build_analysis_context(session) -> str:
    parts: list[str] = []
    prefs = session.generation_prefs or {}
    fmt = session.formatting or {}
    if session.template_source_name:
        parts.append(f"模板:{session.template_source_name}")
    if prefs.get("purpose"):
        parts.append(f"用途:{prefs.get('purpose')}")
    mode = str(prefs.get("target_length_mode") or "").strip().lower()
    val = prefs.get("target_length_value")
    if mode in {"chars", "pages"} and val:
        unit = "字" if mode == "chars" else "页"
        parts.append(f"长度:{val}{unit}")
    if "expand_outline" in prefs:
        parts.append(f"层级展开:{'是' if prefs.get('expand_outline') else '否'}")
    if fmt.get("font_name_east_asia") or fmt.get("font_size_name") or fmt.get("font_size_pt"):
        size = fmt.get("font_size_name") or (f"{fmt.get('font_size_pt')}pt" if fmt.get("font_size_pt") else "")
        parts.append(f"正文:{fmt.get('font_name_east_asia') or ''} {size}".strip())
    if fmt.get("heading1_font_name_east_asia") or fmt.get("heading1_size_pt"):
        parts.append(f"标题:{fmt.get('heading1_font_name_east_asia') or ''} {fmt.get('heading1_size_pt') or ''}pt".strip())
    return "; ".join([p for p in parts if p])

def _normalize_analysis(data: object, raw_text: str) -> dict:
    return prefs_analysis_domain.normalize_analysis(data, raw_text)

def _compose_analysis_input(text: str, analysis: dict) -> str:
    base = str(analysis.get("rewritten_query") or "").strip() or str(text or "").strip()
    parts = [base]
    decomp = analysis.get("decomposition") if isinstance(analysis, dict) else None
    if isinstance(decomp, list) and decomp:
        parts.append("鎷嗚В瑕佺偣:\n- " + "\n- ".join([str(x).strip() for x in decomp if str(x).strip()][:8]))
    intent = analysis.get("intent") if isinstance(analysis, dict) else None
    if isinstance(intent, dict) and intent.get("name"):
        parts.append(f"鎰忓浘: {str(intent.get('name')).strip()}")
    constraints = analysis.get("constraints") if isinstance(analysis, dict) else None
    if isinstance(constraints, list) and constraints:
        parts.append("constraints: " + "; ".join([str(x).strip() for x in constraints if str(x).strip()][:8]))
    missing = analysis.get("missing") if isinstance(analysis, dict) else None
    if isinstance(missing, list) and missing:
        parts.append("missing: " + "; ".join([str(x).strip() for x in missing if str(x).strip()][:8]))
    merged = "\n\n".join([p for p in parts if p])
    return merged.strip()

def _build_pref_summary(raw: str, analysis: dict, title: str, fmt: dict, prefs: dict) -> str:
    return prefs_analysis_domain.build_pref_summary(raw, analysis, title, fmt, prefs)

def _field_confidence(raw: str, analysis: dict, title: str, prefs: dict, fmt: dict) -> dict:
    return prefs_analysis_domain.field_confidence(raw, analysis, title, prefs, fmt)

def _low_conf_questions(conf: dict) -> list[str]:
    return prefs_analysis_domain.low_conf_questions(conf)

def _prioritize_missing(raw: str, analysis: dict, items: list[str]) -> list[str]:
    return prefs_analysis_domain.prioritize_missing(raw, analysis, items)

def _build_missing_questions(title: str, fmt: dict, prefs: dict, analysis: dict) -> list[str]:
    return prefs_analysis_domain.build_missing_questions(title, fmt, prefs, analysis)

def _length_from_text(raw: str) -> tuple[str, int] | None:
    return prefs_analysis_domain.length_from_text(raw)

def _analysis_history_context(session, limit: int = 3) -> str:
    log = list(getattr(session, "analysis_log", []) or [])
    items = []
    for entry in log[-limit:]:
        raw = str(entry.get("raw") or "").strip()
        analysis = entry.get("analysis") if isinstance(entry, dict) else None
        summary = str((analysis or {}).get("rewritten_query") or "").strip() if isinstance(analysis, dict) else ""
        if raw:
            items.append(f"杈撳叆: {raw}")
        if summary and summary != raw:
            items.append(f"鏀瑰啓: {summary}")
    return "\n".join(items)

def _generate_dynamic_questions_with_model(
    *,
    base_url: str,
    model: str,
    raw: str,
    analysis: dict,
    history: str,
    merged: dict,
) -> dict:
    client = OllamaClient(base_url=base_url, model=model, timeout_s=_analysis_timeout_s())
    system = (
        "你是需求解析助手，只输出 JSON，不要 markdown。\n"
        "Schema: {summary:string, questions:[string], confidence:{title:number,purpose:number,length:number,format:number,scope:number,voice:number}}\n"
        "要求：先给 summary，再给不超过 3 条澄清问题 questions，并给出字段置信度 confidence。\n"
        "若信息已足够，questions 可为空。\n"
    )
    payload = {"raw": raw, "analysis": analysis, "history": history, "merged": merged}
    user = (
        f"历史: {history or '空'}\n"
        f"本次输入: {raw}\n"
        f"解析中间结果: {json.dumps(payload, ensure_ascii=False)}\n"
        "Please output JSON following the schema."
    )
    try:
        raw_out = client.chat(system=system, user=user, temperature=0.2)
    except Exception:
        return {}
    raw_json = _extract_json_block(raw_out)
    if not raw_json:
        return {}
    try:
        data = json.loads(raw_json)
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}

def _detect_extract_conflicts(*, analysis: dict, title: str, prefs: dict) -> list[str]:
    return prefs_analysis_domain.detect_extract_conflicts(analysis=analysis, title=title, prefs=prefs)

def _infer_role_defaults(raw: str, prefs: dict, analysis: dict) -> dict:
    return prefs_analysis_domain.infer_role_defaults(raw, prefs, analysis)

def _detect_multi_intent(text: str) -> list[str]:
    return prefs_analysis_domain.detect_multi_intent(text)

def _info_score(title: str, fmt: dict, prefs: dict, analysis: dict) -> int:
    return prefs_analysis_domain.info_score(title, fmt, prefs, analysis)

def _run_message_analysis(session, text: str, *, force: bool = False, quick: bool = False) -> dict:
    raw = str(text or "").strip()
    if not raw:
        return {}
    base = _normalize_analysis({}, raw)
    lower = raw.lower()
    intent_name = "other"
    if any(k in lower for k in ["export", "download", "docx", "pdf"]):
        intent_name = "export"
    elif any(k in lower for k in ["template", "format", "style"]):
        intent_name = "template"
    elif any(k in lower for k in ["upload", "import"]):
        intent_name = "upload"
    elif any(k in lower for k in ["outline", "chapter", "section"]):
        intent_name = "outline"
    elif any(k in lower for k in ["generate", "write", "draft"]):
        intent_name = "generate"

    base["intent"] = {"name": intent_name, "confidence": 0.6 if intent_name != "other" else 0.2, "reason": "heuristic"}
    base["rewritten_query"] = raw
    base["mode"] = "quick" if quick else "normal"
    if hasattr(session, "last_analysis"):
        session.last_analysis = base
    return base

def _classify_upload_with_model(
    *,
    base_url: str,
    model: str,
    filename: str,
    text: str,
) -> dict:
    name = str(filename or "").lower()
    body = str(text or "")
    heading_hits = len(re.findall(r"(?m)^\s*#{1,3}\s+", body))
    kind = "reference"
    if "template" in name or "妯℃澘" in name or heading_hits >= 3:
        kind = "template"
    confidence = 0.7 if kind == "template" else 0.55
    return {"kind": kind, "confidence": confidence, "reason": "heuristic"}

def _extract_template_with_model(
    *,
    base_url: str,
    model: str,
    filename: str,
    text: str,
) -> dict:
    return {}

def _extract_template_refine_with_model(
    *,
    base_url: str,
    model: str,
    filename: str,
    text: str,
    initial: dict,
) -> dict:
    return dict(initial or {})

def _extract_prefs_with_model(
    *,
    base_url: str,
    model: str,
    text: str,
    timeout_s: float,
) -> dict:
    return {}

def _extract_template_titles_with_model(
    *,
    base_url: str,
    model: str,
    filename: str,
    text: str,
) -> dict:
    titles: list[str] = []
    for line in str(text or "").splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            s = re.sub(r"^#+\s*", "", s).strip()
        if len(s) >= 4:
            titles.append(s)
        if len(titles) >= 8:
            break
    return {"titles": titles, "questions": []}

def _extract_prefs_refine_with_model(
    *,
    base_url: str,
    model: str,
    text: str,
    initial: dict,
    timeout_s: float,
) -> dict:
    return dict(initial or {})

def _coerce_float(value: object) -> float | None:
    return prefs_extract_domain.coerce_float(value)

def _coerce_int(value: object) -> int | None:
    return prefs_extract_domain.coerce_int(value)

def _fast_extract_prefs(text: str) -> dict:
    return prefs_extract_domain.fast_extract_prefs(text)

def _normalize_ai_formatting(data: object) -> dict:
    return prefs_extract_domain.normalize_ai_formatting(data)

def _replace_question_headings(text: str) -> str:
    return prefs_extract_domain.replace_question_headings(text)

def _normalize_ai_prefs(data: object) -> dict:
    return prefs_extract_domain.normalize_ai_prefs(data)

def _formatting_from_session(session) -> object:
    from writing_agent.models import FormattingRequirements
    return export_settings_domain.formatting_from_session(
        session,
        formatting_cls=FormattingRequirements,
    )

def _export_prefs_from_session(session) -> ExportPrefs:
    return export_settings_domain.export_prefs_from_session(
        session,
        export_prefs_cls=ExportPrefs,
    )

def _estimate_chars_per_page(formatting: dict, prefs: dict) -> int:
    return length_target_domain.estimate_chars_per_page(formatting, prefs)

def _resolve_target_chars(formatting: dict, prefs: dict) -> int:
    return length_target_domain.resolve_target_chars(formatting, prefs)

def _extract_target_chars_from_instruction(instruction: str) -> int:
    return length_target_domain.extract_target_chars_from_instruction(instruction)

def _json_sections_to_text(data: dict) -> str | None:
    if not isinstance(data, dict):
        return None
    title = str(data.get("title") or "").strip() or _default_title()
    sections = data.get("sections")
    if not isinstance(sections, list):
        return None
    lines: list[str] = [f"# {title}"]
    for sec in sections:
        if not isinstance(sec, dict):
            continue
        sec_title = str(sec.get("title") or "").strip()
        if not sec_title:
            continue
        lines.extend(["", f"## {sec_title}", ""])
        body = sec.get("text")
        if isinstance(body, str) and body.strip():
            lines.append(body.strip())
            continue
        blocks = sec.get("blocks")
        if isinstance(blocks, list):
            for block in blocks:
                if isinstance(block, str):
                    t = block.strip()
                    if t:
                        lines.append(t)
                    continue
                if isinstance(block, dict):
                    t = str(block.get("text") or "").strip()
                    if t:
                        lines.append(t)
    out = "\n".join(lines).strip()
    return out or None
