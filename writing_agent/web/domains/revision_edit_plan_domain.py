"""Revision edit planning and quick/AI edit execution."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Callable

from writing_agent.web.domains.revision_edit_common_domain import (
    EditExecutionResult,
    EditOp,
    EditPlanV2,
    _ALLOWED_EDIT_OPS,
    _clean_section_title,
    _clean_title_candidate,
    _coerce_int,
    _collect_section_titles,
    _escape_prompt_text,
    _extract_json_block,
    _has_confirmation_token,
    _normalize_heading_text,
    _record_edit_plan_metric,
    _parse_chinese_number,
    _requires_confirmation,
    _risk_level_from_ops,
    _split_title_list,
)
from writing_agent.web.domains.revision_edit_ops_domain import (
    _apply_edit_ops,
    _build_quick_edit_note,
    _normalize_edit_instruction_text,
    _parse_edit_ops,
    _strip_quotes,
)

def _normalize_edit_op_item(item: object) -> EditOp | None:
    if not isinstance(item, dict):
        return None
    op = str(item.get("op") or item.get("operation") or "").strip()
    if op not in _ALLOWED_EDIT_OPS:
        return None
    args_in = item.get("args")
    if not isinstance(args_in, dict):
        args_in = {k: v for k, v in item.items() if k not in {"op", "operation", "args"}}
    args: dict[str, Any] = dict(args_in or {})

    if op == "set_title":
        args = {"title": _clean_title_candidate(args.get("title"))}
    elif op == "replace_text":
        old = _strip_quotes(args.get("old"))
        old = re.sub(r"^(?:\u628a|\u5c06)\s*", "", old).strip()
        new = _strip_quotes(args.get("new"))
        args = {"old": old, "new": new, "all": bool(args.get("all"))}
    elif op == "rename_section":
        args = {"old": _clean_section_title(args.get("old")), "new": _clean_section_title(args.get("new"))}
    elif op == "add_section":
        level = _coerce_int(args.get("level"))
        out: dict[str, Any] = {
            "title": _clean_section_title(args.get("title")),
            "anchor": _clean_section_title(args.get("anchor")),
            "position": str(args.get("position") or "after").strip().lower() or "after",
        }
        if level and 1 <= level <= 6:
            out["level"] = level
        args = out
    elif op == "delete_section":
        index_raw = args.get("index")
        index = _coerce_int(index_raw)
        if index is None and index_raw is not None:
            index = _parse_chinese_number(str(index_raw))
        args = {"title": _clean_section_title(args.get("title")), "index": index}
    elif op == "move_section":
        args = {
            "title": _clean_section_title(args.get("title")),
            "anchor": _clean_section_title(args.get("anchor")),
            "position": str(args.get("position") or "after").strip().lower() or "after",
        }
    elif op == "replace_section_content":
        args = {"title": _clean_section_title(args.get("title")), "content": _strip_quotes(args.get("content"))}
    elif op == "append_section_content":
        args = {"title": _clean_section_title(args.get("title")), "content": _strip_quotes(args.get("content"))}
    elif op == "merge_sections":
        args = {"first": _clean_section_title(args.get("first")), "second": _clean_section_title(args.get("second"))}
    elif op == "swap_sections":
        args = {"first": _clean_section_title(args.get("first")), "second": _clean_section_title(args.get("second"))}
    elif op == "split_section":
        new_titles = args.get("new_titles")
        if isinstance(new_titles, list):
            split_titles = [_clean_section_title(x) for x in new_titles]
            split_titles = [x for x in split_titles if x]
        else:
            split_titles = _split_title_list(str(new_titles or ""))
        args = {"title": _clean_section_title(args.get("title")), "new_titles": split_titles}
    elif op == "reorder_sections":
        order = args.get("order")
        if isinstance(order, list):
            items = [_clean_section_title(x) for x in order]
            items = [x for x in items if x]
        else:
            items = _split_title_list(str(order or ""))
        args = {"order": items}
    return EditOp(op=op, args=args)


def _normalize_edit_plan_payload(payload: object, *, source: str) -> EditPlanV2 | None:
    data: dict[str, Any]
    if isinstance(payload, list):
        data = {"operations": payload}
    elif isinstance(payload, dict):
        data = dict(payload)
    else:
        return None
    ops_raw = data.get("operations")
    if not isinstance(ops_raw, list):
        return None
    ops: list[EditOp] = []
    for item in ops_raw:
        op = _normalize_edit_op_item(item)
        if op is None:
            continue
        ops.append(op)
    if not ops:
        return None
    try:
        confidence = float(data.get("confidence") or 0.0)
    except Exception:
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    ambiguities = data.get("ambiguities")
    if isinstance(ambiguities, list):
        ambiguity_list = [str(x).strip() for x in ambiguities if str(x).strip()]
    else:
        ambiguity_list = []
    risk_level = str(data.get("risk_level") or "").strip().lower()
    if risk_level not in {"low", "medium", "high"}:
        risk_level = _risk_level_from_ops(ops)
    requires_confirmation = bool(data.get("requires_confirmation")) or _requires_confirmation(risk_level)
    return EditPlanV2(
        operations=ops,
        version="v2",
        confidence=confidence,
        ambiguities=ambiguity_list,
        requires_confirmation=requires_confirmation,
        risk_level=risk_level,
        source=source,
    )


def _validate_edit_plan(plan: EditPlanV2, text: str) -> tuple[bool, list[str]]:
    warnings: list[str] = []
    errors: list[str] = []
    heading_titles = _collect_section_titles(text)
    heading_keys = {_normalize_heading_text(title) for title in heading_titles}
    section_count = len(heading_titles)

    def has_section(title: str) -> bool:
        key = _normalize_heading_text(title)
        return bool(key) and key in heading_keys

    deleted_titles: set[str] = set()
    for op in plan.operations:
        args = op.args or {}
        kind = op.op
        if kind not in _ALLOWED_EDIT_OPS:
            errors.append(f"unsupported op: {kind}")
            continue
        if kind == "set_title":
            if not str(args.get("title") or "").strip():
                errors.append("set_title.title required")
        elif kind == "replace_text":
            old = str(args.get("old") or "").strip()
            new = str(args.get("new") or "").strip()
            if not old or not new or old == new:
                errors.append("replace_text old/new invalid")
            elif old not in str(text or "") and not bool(args.get("all")):
                warnings.append(f"replace target not found: {old[:30]}")
        elif kind == "rename_section":
            old = str(args.get("old") or "").strip()
            new = str(args.get("new") or "").strip()
            if not old or not new:
                errors.append("rename_section old/new required")
            elif heading_keys and not has_section(old):
                errors.append(f"section not found: {old}")
        elif kind == "add_section":
            if not str(args.get("title") or "").strip():
                errors.append("add_section.title required")
            anchor = str(args.get("anchor") or "").strip()
            if anchor and heading_keys and not has_section(anchor):
                errors.append(f"anchor not found: {anchor}")
        elif kind == "delete_section":
            title = str(args.get("title") or "").strip()
            index = args.get("index")
            if not title and not index:
                errors.append("delete_section needs title or index")
            if title and heading_keys and not has_section(title):
                errors.append(f"section not found: {title}")
            if index is not None:
                try:
                    idx = int(index)
                except Exception:
                    idx = 0
                if idx <= 0:
                    errors.append("delete_section.index must be positive")
                if section_count > 0 and idx > section_count:
                    errors.append(f"delete_section.index out of range: {idx}")
            if title:
                deleted_titles.add(_normalize_heading_text(title))
        elif kind == "move_section":
            title = str(args.get("title") or "").strip()
            anchor = str(args.get("anchor") or "").strip()
            if not title or not anchor:
                errors.append("move_section title/anchor required")
            if heading_keys and title and not has_section(title):
                errors.append(f"section not found: {title}")
            if heading_keys and anchor and not has_section(anchor):
                errors.append(f"anchor not found: {anchor}")
        elif kind in {"replace_section_content", "append_section_content"}:
            title = str(args.get("title") or "").strip()
            content = str(args.get("content") or "").strip()
            if not title or not content:
                errors.append(f"{kind} title/content required")
            if heading_keys and title and not has_section(title):
                errors.append(f"section not found: {title}")
        elif kind in {"merge_sections", "swap_sections"}:
            first = str(args.get("first") or "").strip()
            second = str(args.get("second") or "").strip()
            if not first or not second:
                errors.append(f"{kind} first/second required")
            if heading_keys and first and not has_section(first):
                errors.append(f"section not found: {first}")
            if heading_keys and second and not has_section(second):
                errors.append(f"section not found: {second}")
        elif kind == "split_section":
            title = str(args.get("title") or "").strip()
            new_titles = args.get("new_titles")
            if not title:
                errors.append("split_section.title required")
            if not isinstance(new_titles, list) or len(new_titles) < 2:
                errors.append("split_section.new_titles requires >=2 items")
            if heading_keys and title and not has_section(title):
                errors.append(f"section not found: {title}")
        elif kind == "reorder_sections":
            order = args.get("order")
            if not isinstance(order, list) or not order:
                errors.append("reorder_sections.order required")
            elif heading_keys:
                for item in order:
                    if not has_section(str(item)):
                        errors.append(f"section not found in order: {item}")

        title_ref = str(args.get("title") or "").strip()
        title_key = _normalize_heading_text(title_ref) if title_ref else ""
        if kind != "delete_section" and title_key and title_key in deleted_titles:
            errors.append(f"conflict: operation on deleted section {title_ref}")
    if errors:
        return False, errors
    if warnings:
        for note in warnings:
            if note not in plan.ambiguities:
                plan.ambiguities.append(note)
    return True, []


def _build_model_edit_plan(
    raw: str,
    text: str,
    *,
    get_ollama_settings_fn: Callable[[], Any] | None = None,
    ollama_client_cls: Any = None,
) -> EditPlanV2 | None:
    enabled = os.environ.get("WRITING_AGENT_EDIT_PLAN_ENABLE", "1").strip().lower() not in {"0", "false", "no", "off"}
    if not enabled:
        return None
    if not callable(get_ollama_settings_fn) or ollama_client_cls is None:
        return None
    try:
        settings = get_ollama_settings_fn()
    except Exception:
        return None
    if not getattr(settings, "enabled", False):
        return None
    timeout_s = float(os.environ.get("WRITING_AGENT_EDIT_PLAN_TIMEOUT_S", str(getattr(settings, "timeout_s", 20.0))))
    model = (
        os.environ.get("WRITING_AGENT_EDIT_PLAN_MODEL", "").strip()
        or os.environ.get("WRITING_AGENT_REVISE_MODEL", "").strip()
        or str(getattr(settings, "model", "")).strip()
    )
    if not model:
        return None
    try:
        client = ollama_client_cls(base_url=settings.base_url, model=model, timeout_s=timeout_s)
        if not client.is_running():
            return None
    except Exception:
        return None

    headings = _collect_section_titles(text)[:20]
    heading_hint = ", ".join(headings) if headings else "<none>"
    system = (
        "You are an edit intent planner.\n"
        "Output JSON only. No markdown.\n"
        "Schema:\n"
        "{"
        "\"version\":\"v2\","
        "\"confidence\":0.0-1.0,"
        "\"risk_level\":\"low|medium|high\","
        "\"requires_confirmation\":bool,"
        "\"ambiguities\":[string],"
        "\"operations\":[{\"op\":string,\"args\":object}]"
        "}\n"
        "Allowed op: set_title, replace_text, rename_section, add_section, delete_section, "
        "move_section, replace_section_content, append_section_content, merge_sections, "
        "swap_sections, split_section, reorder_sections.\n"
        "Do not invent sections not present in heading list unless operation does not need a heading."
    )
    user = (
        "<task>plan_edit_operations</task>\n"
        "<constraints>\n"
        "Return strict JSON only.\n"
        "Do not output markdown fences or commentary.\n"
        "Only use known headings for heading-bound operations.\n"
        "</constraints>\n"
        f"<user_instruction>\n{_escape_prompt_text(raw)}\n</user_instruction>\n"
        f"<known_headings>\n{_escape_prompt_text(heading_hint)}\n</known_headings>\n"
        "Return exactly one JSON object following schema."
    )
    try:
        raw_out = client.chat(system=system, user=user, temperature=0.1)
    except Exception:
        return None
    raw_json = _extract_json_block(raw_out)
    if not raw_json:
        return None
    try:
        payload = json.loads(raw_json)
    except Exception:
        return None
    plan = _normalize_edit_plan_payload(payload, source="model")
    if plan is None:
        return None
    ok, _errors = _validate_edit_plan(plan, text)
    if not ok:
        return None
    plan.risk_level = _risk_level_from_ops(plan.operations)
    plan.requires_confirmation = plan.requires_confirmation or _requires_confirmation(plan.risk_level)
    if plan.confidence <= 0:
        plan.confidence = 0.55
    return plan


def _build_rule_edit_plan(raw: str, text: str) -> EditPlanV2 | None:
    ops = _parse_edit_ops(raw)
    if not ops:
        return None
    plan = EditPlanV2(operations=ops, confidence=0.72, source="rules")
    plan.risk_level = _risk_level_from_ops(plan.operations)
    plan.requires_confirmation = _requires_confirmation(plan.risk_level)
    ok, _errors = _validate_edit_plan(plan, text)
    if not ok:
        return None
    return plan


def _build_edit_plan_v2(
    raw: str,
    text: str,
    *,
    prefer_model: bool,
    get_ollama_settings_fn: Callable[[], Any] | None = None,
    ollama_client_cls: Any = None,
) -> EditPlanV2 | None:
    value = _normalize_edit_instruction_text(raw)
    if prefer_model:
        plan = _build_model_edit_plan(
            value,
            text,
            get_ollama_settings_fn=get_ollama_settings_fn,
            ollama_client_cls=ollama_client_cls,
        )
        if plan is not None:
            _record_edit_plan_metric(
                "plan_parsed",
                raw=value,
                prefer_model=True,
                fallback_used=False,
                plan=plan,
                parse_ok=True,
            )
            return plan
        _record_edit_plan_metric(
            "plan_model_miss",
            raw=value,
            prefer_model=True,
            fallback_used=False,
            parse_ok=False,
        )
    rule_plan = _build_rule_edit_plan(value, text)
    if rule_plan is not None:
        _record_edit_plan_metric(
            "plan_parsed",
            raw=value,
            prefer_model=prefer_model,
            fallback_used=prefer_model,
            plan=rule_plan,
            parse_ok=True,
        )
        return rule_plan
    _record_edit_plan_metric(
        "plan_parse_failed",
        raw=value,
        prefer_model=prefer_model,
        fallback_used=prefer_model,
        parse_ok=False,
    )
    return None


def _parse_edit_ops_with_model(
    raw: str,
    text: str,
    *,
    get_ollama_settings_fn: Callable[[], Any] | None = None,
    ollama_client_cls: Any = None,
) -> list[EditOp]:
    plan = _build_model_edit_plan(
        raw,
        text,
        get_ollama_settings_fn=get_ollama_settings_fn,
        ollama_client_cls=ollama_client_cls,
    )
    return list(plan.operations) if plan is not None else []


def _build_plan_note(plan: EditPlanV2) -> str:
    base = _build_quick_edit_note(plan.operations)
    tags = f"source={plan.source};risk={plan.risk_level};confidence={plan.confidence:.2f}"
    if plan.ambiguities:
        return f"{base} [{tags}] ambiguities: " + " | ".join(plan.ambiguities[:2])
    return f"{base} [{tags}]"


def _build_confirmation_note(plan: EditPlanV2) -> str:
    return (
        f"high-risk edit plan detected ({len(plan.operations)} ops). "
        "please append '\u786e\u8ba4\u6267\u884c' to apply. "
        f"[source={plan.source};risk={plan.risk_level}]"
    )


def try_quick_edit(
    text: str,
    instruction: str,
    *,
    looks_like_modify_instruction,
    confirm_apply: bool = False,
    get_ollama_settings_fn: Callable[[], Any] | None = None,
    ollama_client_cls: Any = None,
) -> EditExecutionResult | None:
    raw = (instruction or "").strip()
    if not raw:
        return None
    likely_edit = looks_like_modify_instruction(raw) or bool(
        re.search(r"[\u6539\u5220\u79fb\u66ff\u8c03\u6392\u5408\u62c6\u4f18\u7cbe]", raw)
    )
    plan = _build_edit_plan_v2(
        raw,
        text,
        prefer_model=likely_edit,
        get_ollama_settings_fn=get_ollama_settings_fn,
        ollama_client_cls=ollama_client_cls,
    )
    if plan is None:
        return None
    if plan.requires_confirmation and not (confirm_apply or _has_confirmation_token(raw)):
        _record_edit_plan_metric(
            "apply_blocked",
            raw=raw,
            prefer_model=likely_edit,
            fallback_used=plan.source != "model",
            plan=plan,
            executed=False,
            blocked_reason="confirmation_required",
        )
        return EditExecutionResult(
            text=(text or ""),
            note=_build_confirmation_note(plan),
            applied=False,
            requires_confirmation=True,
            confirmation_reason="high_risk_edit",
            risk_level=plan.risk_level,
            source=plan.source,
            confidence=plan.confidence,
            operations_count=len(plan.operations),
        )
    updated = _apply_edit_ops(text or "", plan.operations)
    if updated.strip() != (text or "").strip():
        _record_edit_plan_metric(
            "apply_executed",
            raw=raw,
            prefer_model=likely_edit,
            fallback_used=plan.source != "model",
            plan=plan,
            executed=True,
        )
        return EditExecutionResult(
            text=updated,
            note=_build_plan_note(plan),
            applied=True,
            requires_confirmation=False,
            confirmation_reason="",
            risk_level=plan.risk_level,
            source=plan.source,
            confidence=plan.confidence,
            operations_count=len(plan.operations),
        )
    _record_edit_plan_metric(
        "apply_no_change",
        raw=raw,
        prefer_model=likely_edit,
        fallback_used=plan.source != "model",
        plan=plan,
        executed=False,
    )
    return None


def _should_try_ai_edit(
    raw: str,
    text: str,
    analysis: dict | None,
    *,
    looks_like_modify_instruction,
) -> bool:
    if not str(text or "").strip():
        return False
    compact = re.sub(r"\s+", "", str(raw or ""))
    if not compact:
        return False
    if re.search(r"(生成|撰写|起草|写一|输出|制作|形成|写作)", compact) and not looks_like_modify_instruction(raw):
        return False
    if looks_like_modify_instruction(raw):
        return True
    if re.search(r"(加上|补上|统一|整理|调整|格式|样式|字体|字号|编号|数字符号|标号|小标题|段落|标题)", compact):
        return True
    if isinstance(analysis, dict):
        intent = analysis.get("intent")
        if isinstance(intent, dict):
            name = str(intent.get("name") or "").strip().lower()
            try:
                conf = float(intent.get("confidence") or 0)
            except Exception:
                conf = 0.0
            if name in {"modify", "format", "outline"} and conf >= 0.3:
                return True
            if name == "generate" and conf >= 0.6:
                return False
    return False


def try_ai_intent_edit(
    text: str,
    instruction: str,
    analysis: dict | None = None,
    *,
    looks_like_modify_instruction,
    confirm_apply: bool = False,
    get_ollama_settings_fn: Callable[[], Any] | None = None,
    ollama_client_cls: Any = None,
) -> EditExecutionResult | None:
    if not _should_try_ai_edit(instruction, text, analysis, looks_like_modify_instruction=looks_like_modify_instruction):
        return None
    plan = _build_edit_plan_v2(
        instruction,
        text,
        prefer_model=True,
        get_ollama_settings_fn=get_ollama_settings_fn,
        ollama_client_cls=ollama_client_cls,
    )
    if plan is None:
        return None
    if plan.requires_confirmation and not (confirm_apply or _has_confirmation_token(instruction)):
        _record_edit_plan_metric(
            "apply_blocked",
            raw=instruction,
            prefer_model=True,
            fallback_used=plan.source != "model",
            plan=plan,
            executed=False,
            blocked_reason="confirmation_required",
        )
        return EditExecutionResult(
            text=(text or ""),
            note=_build_confirmation_note(plan),
            applied=False,
            requires_confirmation=True,
            confirmation_reason="high_risk_edit",
            risk_level=plan.risk_level,
            source=plan.source,
            confidence=plan.confidence,
            operations_count=len(plan.operations),
        )
    updated = _apply_edit_ops(text or "", plan.operations)
    if updated.strip() != (text or "").strip():
        _record_edit_plan_metric(
            "apply_executed",
            raw=instruction,
            prefer_model=True,
            fallback_used=plan.source != "model",
            plan=plan,
            executed=True,
        )
        return EditExecutionResult(
            text=updated,
            note=_build_plan_note(plan),
            applied=True,
            requires_confirmation=False,
            confirmation_reason="",
            risk_level=plan.risk_level,
            source=plan.source,
            confidence=plan.confidence,
            operations_count=len(plan.operations),
        )
    _record_edit_plan_metric(
        "apply_no_change",
        raw=instruction,
        prefer_model=True,
        fallback_used=plan.source != "model",
        plan=plan,
        executed=False,
    )
    return None


__all__ = [
    name
    for name in globals()
    if not name.startswith("__")
    and name not in {
        "re",
        "EditExecutionResult",
        "EditPlanV2",
        "_ALLOWED_EDIT_OPS",
        "_CONFIRM_TOKENS_RE",
        "_HIGH_RISK_OPS",
        "_LOW_RISK_OPS",
        "_MEDIUM_RISK_OPS",
        "_clean_title_candidate",
        "_coerce_int",
        "_collect_section_titles",
        "_escape_prompt_text",
        "_extract_json_block",
        "_extract_tag_block",
        "_normalize_heading_text",
        "_record_edit_plan_metric",
        "_apply_edit_ops",
        "_build_quick_edit_note",
        "_extract_replace_pair",
        "_extract_title_change",
        "_load_edit_rules",
        "_normalize_edit_instruction_text",
        "_parse_edit_ops",
    }
]
