"""Revision edit rule parsing and edit operation application helpers."""

from __future__ import annotations

import json
import re
from pathlib import Path

from writing_agent.web.domains import section_edit_ops_domain
from writing_agent.web.domains.revision_edit_common_domain import (
    EditOp,
    RuleSpec,
    _EDIT_RULES_CACHE,
    _clean_section_title,
    _clean_title_candidate,
    _normalize_heading_text,
    _parse_chinese_number,
    _split_title_list,
)

def _compile_rule_flags(flag_list: list[str]) -> int:
    flags = 0
    for flag in flag_list or []:
        value = str(flag).upper()
        if value == "I":
            flags |= re.IGNORECASE
        elif value == "M":
            flags |= re.MULTILINE
        elif value == "S":
            flags |= re.DOTALL
        elif value == "X":
            flags |= re.VERBOSE
    return flags


def _load_edit_rules() -> list[RuleSpec]:
    path = Path("writing_agent/web/edit_rules.json")
    try:
        mtime = path.stat().st_mtime
    except Exception:
        return []
    cache = _EDIT_RULES_CACHE
    if cache.get("mtime") == mtime and cache.get("rules"):
        return cache.get("rules") or []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    rules: list[RuleSpec] = []
    for item in data.get("rules", []):
        pattern = str(item.get("pattern") or "").strip()
        if not pattern:
            continue
        flags = _compile_rule_flags(item.get("flags") or [])
        try:
            regex = re.compile(pattern, flags)
        except re.error:
            continue
        rules.append(
            RuleSpec(
                op=str(item.get("op") or ""),
                regex=regex,
                args=dict(item.get("args") or {}),
                priority=int(item.get("priority") or 100),
                clean=list(item.get("clean") or []),
                clean_title=bool(item.get("clean_title") or False),
                strip_quotes=list(item.get("strip_quotes") or []),
                types=dict(item.get("types") or {}),
                detect_all=bool(item.get("detect_all") or False),
            )
        )
    rules.sort(key=lambda r: r.priority)
    _EDIT_RULES_CACHE["mtime"] = mtime
    _EDIT_RULES_CACHE["rules"] = rules
    return rules


def _split_instruction_clauses(raw: str) -> list[str]:
    value = str(raw or "").strip()
    if not value:
        return []
    token = "||"
    for sep in [" and ", " then ", " also ", " plus ", "并且", "然后", "同时", "另外"]:
        value = value.replace(sep, token)
    value = re.sub(r"[,;，；。]+", token, value)
    parts = [p.strip() for p in value.split(token) if p.strip()]
    return parts or [str(raw or "").strip()]


def _normalize_edit_instruction_text(raw: str) -> str:
    value = str(raw or "").strip()
    if not value:
        return ""
    # Normalize frequent colloquial patterns before rule parsing.
    value = value.replace("\u6539\u4e00\u4e0b", "\u6539\u4e3a")
    value = value.replace("\u6362\u4e00\u4e0b", "\u6362\u6210")
    value = value.replace("\u6316\u5230", "\u79fb\u5230")
    value = value.replace("\u632a\u5230", "\u79fb\u5230")
    value = value.replace("\u4e0d\u8981\u4e86", "\u5220\u9664")
    value = re.sub(
        r"\u7b2c\s*([0-9\u4e00-\u4e5d\u5341]+)\s*(?:\u7ae0|\u8282)\s*\u5220\u9664?",
        "\u5220\u9664\u7b2c\\1\u8282",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(
        r"\u7b2c\s*([0-9\u4e00-\u4e5d\u5341]+)\s*(?:\u7ae0|\u8282)\s*\u4e0d\u8981\u4e86",
        "\u5220\u9664\u7b2c\\1\u8282",
        value,
        flags=re.IGNORECASE,
    )
    return value


def _strip_quotes(text: str) -> str:
    return str(text or "").strip().strip("\"'[]{}")


def _build_rule_args(rule: RuleSpec, match: re.Match, clause: str) -> dict | None:
    args: dict = {}
    for key, val in (rule.args or {}).items():
        if isinstance(val, str) and val.startswith("$"):
            group = val[1:]
            try:
                args[key] = match.group(group)
            except Exception:
                args[key] = ""
        else:
            args[key] = val
    if rule.detect_all:
        args["all"] = bool(re.search(r"(全部|所有|全文|all)", clause, flags=re.IGNORECASE))
    for key in rule.strip_quotes or []:
        if key in args:
            args[key] = _strip_quotes(args.get(key))
    if rule.clean_title and "title" in args:
        args["title"] = _clean_title_candidate(args.get("title"))
    for key in rule.clean or []:
        if key in args:
            args[key] = _clean_section_title(args.get(key))
    for key, kind in (rule.types or {}).items():
        if key not in args:
            continue
        if kind == "int_chinese":
            args[key] = _parse_chinese_number(str(args.get(key)))
        elif kind == "list_titles":
            args[key] = _split_title_list(str(args.get(key)))
    for key in list(args.keys()):
        if isinstance(args[key], str) and not args[key].strip():
            args[key] = ""
    if rule.op == "replace_text":
        old = str(args.get("old") or "").strip()
        if old:
            old = re.sub(r"^(?:\u628a|\u5c06)\s*", "", old).strip()
            args["old"] = old
    return args


def _extract_title_change(raw: str) -> str | None:
    value = (raw or "").strip()
    if not value:
        return None
    patterns = [
        r"(?:修改|更改|调整|设置)\s*(?:文档)?(?:标题|题目)\s*(?:为|成)?\s*(.+)",
        r"(?:标题|题目)\s*(?:改为|改成|调整为|设置为)\s*(.+)",
        r"把\s*(?:文档)?(?:标题|题目)\s*(?:改为|改成|调整为|设置为)\s*(.+)",
        r"将\s*(?:文档)?(?:标题|题目)\s*(?:改为|改成|调整为|设置为)\s*(.+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, value)
        if match:
            candidate = _clean_title_candidate(match.group(1))
            if candidate:
                return candidate
    return None


def _extract_replace_pair(raw: str) -> tuple[str, str] | None:
    value = (raw or "").strip()
    if not value:
        return None
    quoted = re.search(
        r"[把将]?\s*[\"“”‘’《》](.{1,80}?)[\"“”‘’《》]\s*(?:改为|改成|替换为|换成)\s*[\"“”‘’《》](.{1,80}?)[\"“”‘’《》]\s*$",
        value,
    )
    if quoted:
        old = quoted.group(1).strip()
        new = quoted.group(2).strip()
        if old and new and old != new:
            return old, new
    match = re.search(r"(.{1,80}?)\s*(?:改为|改成|替换为|换成)\s*(.{1,80})", value)
    if match:
        old = match.group(1).strip().strip("\"'[]{}")
        new = match.group(2).strip().strip("\"'[]{}")
        if old and new and old != new:
            return old, new
    return None


def _apply_title_change(text: str, title: str) -> str:
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    for idx, line in enumerate(lines):
        if re.match(r"^#\s+", line):
            lines[idx] = f"# {title}"
            return "\n".join(lines).strip()
    if lines and lines[0].strip():
        return f"# {title}\n\n" + "\n".join(lines).strip()
    return f"# {title}\n" + "\n".join(lines).strip()


def _apply_set_title(text: str, title: str) -> str:
    return section_edit_ops_domain.apply_set_title(text, title, apply_title_change=_apply_title_change)


def _apply_replace_text(text: str, old: str, new: str, *, replace_all: bool = False) -> str:
    return section_edit_ops_domain.apply_replace_text(text, old, new, replace_all=replace_all)


def _apply_rename_section(text: str, old_title: str, new_title: str) -> str:
    return section_edit_ops_domain.apply_rename_section(
        text,
        old_title,
        new_title,
        normalize_heading_text=_normalize_heading_text,
    )


def _apply_add_section_op(
    text: str,
    title: str,
    *,
    anchor: str | None = None,
    position: str = "after",
    level: int | None = None,
) -> str:
    return section_edit_ops_domain.apply_add_section_op(
        text,
        title,
        anchor=anchor,
        position=position,
        level=level,
        normalize_heading_text=_normalize_heading_text,
    )


def _apply_delete_section_op(text: str, title: str | None = None, index: int | None = None) -> str:
    return section_edit_ops_domain.apply_delete_section_op(
        text,
        title=title,
        index=index,
        normalize_heading_text=_normalize_heading_text,
    )


def _apply_move_section_op(text: str, title: str, anchor: str, *, position: str = "after") -> str:
    return section_edit_ops_domain.apply_move_section_op(
        text,
        title,
        anchor,
        position=position,
        normalize_heading_text=_normalize_heading_text,
    )


def _apply_replace_section_content_op(text: str, title: str, content: str) -> str:
    return section_edit_ops_domain.apply_replace_section_content_op(
        text,
        title,
        content,
        normalize_heading_text=_normalize_heading_text,
    )


def _apply_append_section_content_op(text: str, title: str, content: str) -> str:
    return section_edit_ops_domain.apply_append_section_content_op(
        text,
        title,
        content,
        normalize_heading_text=_normalize_heading_text,
    )


def _apply_merge_sections_op(text: str, first: str, second: str) -> str:
    return section_edit_ops_domain.apply_merge_sections_op(
        text,
        first,
        second,
        normalize_heading_text=_normalize_heading_text,
    )


def _apply_swap_sections_op(text: str, first: str, second: str) -> str:
    return section_edit_ops_domain.apply_swap_sections_op(
        text,
        first,
        second,
        normalize_heading_text=_normalize_heading_text,
    )


def _apply_split_section_op(text: str, title: str, new_titles: list[str]) -> str:
    return section_edit_ops_domain.apply_split_section_op(
        text,
        title,
        new_titles,
        normalize_heading_text=_normalize_heading_text,
    )


def _apply_reorder_sections_op(text: str, order: list[str]) -> str:
    return section_edit_ops_domain.apply_reorder_sections_op(
        text,
        order,
        normalize_heading_text=_normalize_heading_text,
    )


def _apply_edit_op(text: str, op: EditOp) -> str:
    kind = op.op
    args = op.args or {}
    if kind == "set_title":
        return _apply_set_title(text, str(args.get("title") or ""))
    if kind == "replace_text":
        return _apply_replace_text(text, str(args.get("old") or ""), str(args.get("new") or ""), replace_all=bool(args.get("all")))
    if kind == "rename_section":
        return _apply_rename_section(text, str(args.get("old") or ""), str(args.get("new") or ""))
    if kind == "add_section":
        return _apply_add_section_op(
            text,
            str(args.get("title") or ""),
            anchor=str(args.get("anchor") or "") or None,
            position=str(args.get("position") or "after"),
            level=args.get("level"),
        )
    if kind == "delete_section":
        index = args.get("index")
        return _apply_delete_section_op(text, title=str(args.get("title") or "") or None, index=int(index or 0) or None)
    if kind == "move_section":
        return _apply_move_section_op(
            text,
            str(args.get("title") or ""),
            str(args.get("anchor") or ""),
            position=str(args.get("position") or "after"),
        )
    if kind == "replace_section_content":
        return _apply_replace_section_content_op(text, str(args.get("title") or ""), str(args.get("content") or ""))
    if kind == "append_section_content":
        return _apply_append_section_content_op(text, str(args.get("title") or ""), str(args.get("content") or ""))
    if kind == "merge_sections":
        return _apply_merge_sections_op(text, str(args.get("first") or ""), str(args.get("second") or ""))
    if kind == "swap_sections":
        return _apply_swap_sections_op(text, str(args.get("first") or ""), str(args.get("second") or ""))
    if kind == "split_section":
        titles = args.get("new_titles")
        if not isinstance(titles, list):
            titles = []
        return _apply_split_section_op(text, str(args.get("title") or ""), [str(t) for t in titles if str(t).strip()])
    if kind == "reorder_sections":
        order = args.get("order")
        if not isinstance(order, list):
            order = []
        return _apply_reorder_sections_op(text, [str(t) for t in order if str(t).strip()])
    return text


def _apply_edit_ops(text: str, ops: list[EditOp]) -> str:
    cur = text or ""
    for op in ops:
        cur = _apply_edit_op(cur, op)
    return cur


def _parse_edit_ops(raw: str) -> list[EditOp]:
    value = (raw or "").strip()
    if not value:
        return []
    value = re.sub(r"^(请|麻烦|帮我|请帮我|帮忙)", "", value).strip()
    value = _normalize_edit_instruction_text(value)
    clauses = _split_instruction_clauses(value)
    rules = _load_edit_rules()
    ops: list[EditOp] = []
    if rules:
        for clause in clauses:
            matched = False
            for rule in rules:
                if not rule.op:
                    continue
                m = rule.regex.search(clause)
                if not m:
                    continue
                args = _build_rule_args(rule, m, clause)
                if args is None:
                    continue
                ops.append(EditOp(rule.op, args))
                matched = True
                break
            if not matched and len(clauses) == 1:
                break
    if ops:
        return ops

    title = _extract_title_change(value)
    if title:
        return [EditOp("set_title", {"title": title})]
    pair = _extract_replace_pair(value)
    if pair:
        old, new = pair
        replace_all = bool(re.search(r"(全部|所有|全文|all)", value, flags=re.IGNORECASE))
        return [EditOp("replace_text", {"old": old, "new": new, "all": replace_all})]
    return []


def _build_quick_edit_note(ops: list[EditOp]) -> str:
    if not ops:
        return "quick edit applied"
    if len(ops) > 1:
        return f"quick edit applied ({len(ops)} operations)"
    op = ops[0]
    args = op.args or {}
    if op.op == "set_title":
        return f"title updated: {args.get('title', '')}"
    if op.op == "replace_text":
        return "text replaced"
    if op.op == "rename_section":
        return f"section renamed: {args.get('new', '')}"
    if op.op == "add_section":
        return f"section added: {args.get('title', '')}"
    if op.op == "delete_section":
        if args.get("index"):
            return f"section deleted at index {args.get('index')}"
        return f"section deleted: {args.get('title', '')}"
    if op.op == "move_section":
        return f"section moved: {args.get('title', '')}"
    if op.op == "replace_section_content":
        return f"section content replaced: {args.get('title', '')}"
    if op.op == "append_section_content":
        return f"section content appended: {args.get('title', '')}"
    if op.op == "merge_sections":
        return "sections merged"
    if op.op == "swap_sections":
        return "sections swapped"
    if op.op == "split_section":
        return "section split"
    if op.op == "reorder_sections":
        return "sections reordered"
    return "quick edit applied"


__all__ = [
    name
    for name in globals()
    if not name.startswith("__")
    and name not in {
        "re",
        "section_edit_ops_domain",
        "EditOp",
        "RuleSpec",
        "_EDIT_RULES_CACHE",
        "_clean_section_title",
        "_normalize_heading_text",
        "_parse_chinese_number",
        "_split_title_list",
    }
]
