"""Version State Domain module.

This module belongs to `writing_agent.web.domains` in the writing-agent codebase.
"""

from __future__ import annotations

from typing import Any, Callable


def version_kind_from_tags(tags: Any) -> str:
    if not isinstance(tags, list):
        return ""
    if "major" in tags:
        return "major"
    if "minor" in tags:
        return "minor"
    return ""


def version_diff_summary(
    prev_doc_ir: dict,
    next_doc_ir: dict,
    *,
    doc_ir_from_dict: Callable[[dict], Any],
    doc_ir_diff: Callable[[Any, Any], list[tuple[str, Any, Any]]],
) -> dict:
    try:
        old_doc = doc_ir_from_dict(prev_doc_ir or {})
        new_doc = doc_ir_from_dict(next_doc_ir or {})
        diff = doc_ir_diff(old_doc, new_doc)
    except Exception:
        return {}
    counts = {"insert": 0, "delete": 0, "replace": 0}
    for op, _, _ in diff:
        if op in counts:
            counts[op] += 1
    return counts


def get_current_branch(session: Any) -> str:
    if not getattr(session, "current_version_id", None):
        return "main"
    versions = getattr(session, "versions", None) or {}
    current = versions.get(session.current_version_id)
    return str(getattr(current, "branch_name", "") or "main")


def auto_commit_version(
    session: Any,
    message: str,
    *,
    author: str,
    tags: list[str] | None,
    get_current_branch_fn: Callable[[Any], str],
    version_node_cls: Any,
    version_id_factory: Callable[[], str],
    now_ts: Callable[[], float],
) -> str | None:
    if session is None:
        return None
    text = str(getattr(session, "doc_text", "") or "").strip()
    if not text:
        return None
    doc_ir = session.doc_ir.copy() if getattr(session, "doc_ir", None) else {}
    tag_list = list(tags or [])
    if "minor" not in tag_list:
        tag_list.append("minor")
    if "auto" not in tag_list:
        tag_list.append("auto")
    cur_id = getattr(session, "current_version_id", None)
    versions = getattr(session, "versions", None) or {}
    if cur_id and cur_id in versions:
        cur = versions.get(cur_id)
        if cur and str(getattr(cur, "doc_text", "") or "").strip() == text and (getattr(cur, "doc_ir", None) or {}) == (doc_ir or {}):
            return None
    version_id = version_id_factory()
    branch = get_current_branch_fn(session)
    version = version_node_cls(
        version_id=version_id,
        parent_id=session.current_version_id,
        timestamp=now_ts(),
        message=message or "auto commit",
        author=author,
        doc_text=session.doc_text,
        doc_ir=session.doc_ir.copy() if session.doc_ir else {},
        tags=tag_list,
        branch_name=branch,
    )
    session.versions[version_id] = version
    session.current_version_id = version_id
    session.branches[branch] = version_id
    return version_id
