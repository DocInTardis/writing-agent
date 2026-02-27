"""Export Structure Domain module.

This module belongs to `writing_agent.web.domains` in the writing-agent codebase.
"""

from __future__ import annotations

import os
import re
import time
from typing import Any, Callable

_TOC_HEADING_RE = re.compile(
    r"^#{1,3}\s*(?:\u76ee\u5f55|\u76ee\u6b21|table\s+of\s+contents|contents?)\s*$",
    flags=re.IGNORECASE | re.MULTILINE,
)
_REFERENCE_HEADING_RE = re.compile(
    r"^#{1,3}\s*(?:\u53c2\u8003\u6587\u732e|\u53c2\u8003\u8d44\u6599|references?|bibliography)\s*$",
    flags=re.IGNORECASE | re.MULTILINE,
)
_CITATION_KEY_RE = re.compile(r"\[@([a-zA-Z0-9_-]+)\]")

_MSG_MISSING_TOC = "\u7f3a\u5c11\u76ee\u5f55\u7ae0\u8282\u3002"
_MSG_MISSING_REFERENCES = "\u7f3a\u5c11\u53c2\u8003\u6587\u732e\u7ae0\u8282\u3002"
_MSG_REFERENCES_NOT_LAST = "\u53c2\u8003\u6587\u732e\u7ae0\u8282\u5fc5\u987b\u4f4d\u4e8e\u6587\u672b\u3002"
_MSG_HEADING_GLUE = "\u68c0\u6d4b\u5230\u6807\u9898\u7c98\u8fde\u6216\u4e2d\u82f1\u6587\u91cd\u590d\u6807\u9898\u3002"
_MSG_AUTOFIX_APPLIED = (
    "\u5bfc\u51fa\u524d\u5df2\u81ea\u52a8\u4fee\u590d\u76ee\u5f55/\u53c2\u8003\u6587\u732e/\u6807\u9898\u7ed3\u6784\u95ee\u9898\u3002"
)
_MSG_CITATION_MISSING_METADATA = (
    "\u6587\u6863\u4e2d\u5b58\u5728\u672a\u767b\u8bb0\u7684\u5f15\u7528\u952e\uff0c\u5bfc\u51fa\u5df2\u963b\u6b62\u3002"
)
_MSG_CITATION_UNVERIFIED = (
    "\u6587\u6863\u4e2d\u5b58\u5728\u672a\u6821\u9a8c\u901a\u8fc7\u7684\u5f15\u7528\uff0c\u5bfc\u51fa\u5df2\u963b\u6b62\u3002"
)
_MSG_CITATION_VERIFY_STALE = (
    "\u5f15\u7528\u6821\u9a8c\u7ed3\u679c\u5df2\u8fc7\u671f\uff0c\u8bf7\u91cd\u65b0\u6821\u9a8c\u540e\u5bfc\u51fa\u3002"
)


def has_toc_heading(text: str) -> bool:
    src = str(text or "")
    if not src:
        return False
    return bool(_TOC_HEADING_RE.search(src))


def has_reference_heading(text: str) -> bool:
    src = str(text or "")
    if not src:
        return False
    return bool(_REFERENCE_HEADING_RE.search(src))


def collect_toc_titles(
    text: str,
    *,
    extract_sections: Callable[..., list[Any]],
    is_reference_section: Callable[[str], bool],
) -> list[str]:
    sections = extract_sections(text, prefer_levels=(2, 3))
    out: list[str] = []
    seen: set[str] = set()
    for sec in sections:
        title = str(getattr(sec, "title", "") or "").strip()
        if not title:
            continue
        if is_reference_section(title):
            continue
        if has_toc_heading(f"## {title}"):
            continue
        if title in seen:
            continue
        seen.add(title)
        out.append(title)
    return out


def ensure_toc_section(
    text: str,
    *,
    extract_sections: Callable[..., list[Any]],
    is_reference_section: Callable[[str], bool],
    split_lines: Callable[[str], list[str]],
) -> str:
    src = str(text or "").strip()
    if not src or has_toc_heading(src):
        return src
    titles = collect_toc_titles(
        src,
        extract_sections=extract_sections,
        is_reference_section=is_reference_section,
    )
    if len(titles) < 1:
        return src
    lines = split_lines(src)
    insert_idx = 0
    if lines and re.match(r"^#\s+.+", lines[0].strip()):
        insert_idx = 1
        while insert_idx < len(lines) and not lines[insert_idx].strip():
            insert_idx += 1
    toc_lines = ["## \u76ee\u5f55", ""] + [f"{idx}. {title}" for idx, title in enumerate(titles, start=1)] + [""]
    lines[insert_idx:insert_idx] = toc_lines
    return "\n".join(lines).strip()


def reference_lines_from_session(
    session: Any,
    *,
    citation_style_from_session: Callable[[Any], Any],
    format_reference: Callable[[Any, Any], str],
) -> list[str]:
    if session is None:
        return []
    citations = session.citations if isinstance(getattr(session, "citations", None), dict) else {}
    if not citations:
        return []
    style = citation_style_from_session(session)
    out: list[str] = []
    for idx, key in enumerate(citations.keys(), start=1):
        cite = citations.get(key)
        try:
            body = format_reference(cite, style) if cite else f"{key} (citation metadata missing)"
        except Exception:
            body = str(getattr(cite, "title", "") or key)
        out.append(f"[{idx}] {body}")
    return out


def ensure_reference_section(
    text: str,
    session: Any,
    *,
    has_reference_heading_fn: Callable[[str], bool],
    reference_lines_from_session_fn: Callable[[Any], list[str]],
    insert_reference_section: Callable[[str, list[str]], str],
) -> str:
    src = str(text or "").strip()
    if not src or has_reference_heading_fn(src):
        return src
    ref_lines = reference_lines_from_session_fn(session)
    if not ref_lines:
        return src
    return insert_reference_section(src, ref_lines)


def reference_section_last(
    text: str,
    *,
    extract_sections: Callable[..., list[Any]],
    is_reference_section: Callable[[str], bool],
) -> bool:
    sections = extract_sections(text, prefer_levels=(1, 2, 3))
    if not sections:
        return True
    ref_idx = -1
    for i, sec in enumerate(sections):
        if is_reference_section(str(getattr(sec, "title", "") or "")):
            ref_idx = i
            break
    if ref_idx < 0:
        return False
    return ref_idx == (len(sections) - 1)


def move_reference_section_to_end(
    text: str,
    *,
    extract_sections: Callable[..., list[Any]],
    is_reference_section: Callable[[str], bool],
    apply_move_section_op: Callable[..., str],
) -> str:
    sections = extract_sections(text, prefer_levels=(1, 2, 3))
    if len(sections) <= 1:
        return text
    ref = None
    for sec in sections:
        if is_reference_section(str(getattr(sec, "title", "") or "")):
            ref = sec
            break
    if ref is None:
        return text
    if getattr(sections[-1], "start", -1) == getattr(ref, "start", -2) and getattr(sections[-1], "end", -1) == getattr(ref, "end", -2):
        return text
    anchor = sections[-1]
    try:
        return apply_move_section_op(
            text,
            str(getattr(ref, "title", "") or ""),
            str(getattr(anchor, "title", "") or ""),
            position="after",
        )
    except Exception:
        return text


def extract_citation_keys_from_text(text: str) -> list[str]:
    src = str(text or "")
    if not src:
        return []
    return sorted(set(_CITATION_KEY_RE.findall(src)))


def has_reference_requirement(
    session: Any,
    text: str,
    *,
    has_reference_heading_fn: Callable[[str], bool],
    reference_lines_from_session_fn: Callable[[Any], list[str]],
) -> bool:
    src = str(text or "")
    if not src:
        return False
    if has_reference_heading_fn(src):
        return True
    if extract_citation_keys_from_text(src):
        return True
    return bool(reference_lines_from_session_fn(session))


def citation_export_issues(
    session: Any,
    text: str,
    *,
    strict_citation_verify_enabled: Callable[[Any], bool],
    get_internal_pref: Callable[[Any, str, Any], Any],
    citation_verify_key: str,
    allow_possible_citation_status: Callable[[Any], bool],
) -> list[dict]:
    if not strict_citation_verify_enabled(session):
        return []

    cite_keys = extract_citation_keys_from_text(text)
    if not cite_keys:
        return []

    citations = session.citations if isinstance(getattr(session, "citations", None), dict) else {}
    verify_raw = get_internal_pref(session, citation_verify_key, {}) or {}
    verify_obj = verify_raw if isinstance(verify_raw, dict) else {}
    verify_items = verify_obj.get("items") if isinstance(verify_obj.get("items"), dict) else {}
    updated_at = float(verify_obj.get("updated_at") or 0.0)

    max_age_h_raw = os.environ.get("WRITING_AGENT_CITATION_VERIFY_MAX_AGE_H", "168").strip()
    try:
        max_age_h = max(1.0, float(max_age_h_raw))
    except Exception:
        max_age_h = 168.0

    is_stale = updated_at <= 0 or (time.time() - updated_at) > max_age_h * 3600.0
    allow_possible = allow_possible_citation_status(session)

    missing_meta: list[str] = []
    unverified: list[str] = []
    for key in cite_keys:
        if key not in citations:
            missing_meta.append(key)
            continue
        row = verify_items.get(key) if isinstance(verify_items, dict) else None
        status = str(row.get("status") or "") if isinstance(row, dict) else ""
        if status == "verified":
            continue
        if allow_possible and status == "possible":
            continue
        unverified.append(key)

    issues: list[dict] = []
    if missing_meta:
        issues.append(
            {
                "code": "citation_missing_metadata",
                "message": _MSG_CITATION_MISSING_METADATA,
                "blocking": True,
                "keys": missing_meta,
            }
        )
    if unverified:
        issues.append(
            {
                "code": "citation_unverified",
                "message": _MSG_CITATION_UNVERIFIED,
                "blocking": True,
                "keys": unverified,
            }
        )
    if not issues and is_stale:
        issues.append(
            {
                "code": "citation_verify_stale",
                "message": _MSG_CITATION_VERIFY_STALE,
                "blocking": True,
                "keys": cite_keys,
            }
        )
    return issues


def export_quality_report(
    session: Any,
    text: str,
    *,
    auto_fix: bool,
    export_gate_policy: Callable[[Any], str],
    strict_doc_format_enabled: Callable[[Any], bool],
    has_reference_requirement_fn: Callable[[Any, str], bool],
    normalize_export_text: Callable[..., str],
    ensure_toc_section_fn: Callable[[str], str],
    ensure_reference_section_fn: Callable[[str, Any], str],
    move_reference_section_to_end_fn: Callable[[str], str],
    has_toc_heading_fn: Callable[[str], bool],
    has_reference_heading_fn: Callable[[str], bool],
    reference_section_last_fn: Callable[[str], bool],
    citation_export_issues_fn: Callable[[Any, str], list[dict]],
) -> dict:
    policy = export_gate_policy(session)
    src = str(text or "").strip()
    fixed = src
    issues: list[dict] = []
    warnings: list[dict] = []

    strict_doc_format = strict_doc_format_enabled(session)
    if strict_doc_format and fixed:
        before = fixed
        require_references = has_reference_requirement_fn(session, fixed)
        if auto_fix:
            fixed = normalize_export_text(fixed, session=session)
            fixed = ensure_toc_section_fn(fixed)
            if require_references:
                fixed = ensure_reference_section_fn(fixed, session)
                fixed = move_reference_section_to_end_fn(fixed)
            fixed = normalize_export_text(fixed, session=session)
            require_references = has_reference_requirement_fn(session, fixed)
        if not has_toc_heading_fn(fixed):
            issues.append({"code": "missing_toc", "message": _MSG_MISSING_TOC, "blocking": True})
        if require_references and not has_reference_heading_fn(fixed):
            issues.append({"code": "missing_references", "message": _MSG_MISSING_REFERENCES, "blocking": True})
        if require_references and has_reference_heading_fn(fixed) and not reference_section_last_fn(fixed):
            issues.append({"code": "references_not_last", "message": _MSG_REFERENCES_NOT_LAST, "blocking": True})
        probe = normalize_export_text(fixed, session=session)
        if probe != fixed:
            issues.append({"code": "heading_glue", "message": _MSG_HEADING_GLUE, "blocking": True})
        if auto_fix and before != fixed:
            warnings.append({"code": "autofix_applied", "message": _MSG_AUTOFIX_APPLIED})

    issues.extend(citation_export_issues_fn(session, fixed or src))

    normalized_issues: list[dict] = []
    for item in issues:
        if not isinstance(item, dict):
            continue
        row = dict(item)
        is_blocking = bool(row.get("blocking", True))
        if policy != "strict":
            if policy == "warn" and is_blocking:
                warnings.append(
                    {
                        "code": "policy_warn",
                        "from": str(row.get("code") or ""),
                        "message": str(row.get("message") or row.get("code") or "export issue"),
                    }
                )
            row["blocking"] = False
        else:
            row["blocking"] = is_blocking
        normalized_issues.append(row)

    can_export = True if policy in {"warn", "off"} else not any(bool(x.get("blocking", True)) for x in normalized_issues)
    return {
        "policy": policy,
        "can_export": can_export,
        "issues": normalized_issues,
        "warnings": warnings,
        "fixed_text": fixed if auto_fix else "",
    }
