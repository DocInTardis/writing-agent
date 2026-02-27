"""Revision Edit Runtime Domain module.

This module belongs to `writing_agent.web.domains` in the writing-agent codebase.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from writing_agent.web.domains import section_edit_ops_domain


def _normalize_heading_text(text: str) -> str:
    value = re.sub(r"^#{1,6}\s*", "", str(text or "")).strip()
    value = re.sub(r"^第[一二三四五六七八九十百千万零两0-9]+[章节部分]\s*", "", value)
    value = re.sub(r"^(?:\d+(?:\.\d+){0,3}|[一二三四五六七八九十百千万零两]+)[\.\uFF0E\u3001\)]\s*", "", value)
    return re.sub(r"\s+", "", value)


def _clean_title_candidate(text: str) -> str:
    value = str(text or "").strip()
    if not value:
        return ""
    quoted = re.search(r"[\"'“”‘’《》](.{1,80}?)[\"'“”‘’《》]", value)
    if quoted:
        value = quoted.group(1)
    value = value.strip().strip("\"'[]{}<>")
    value = re.sub(r"[,.;:!?，。！？；：]+$", "", value).strip()
    return value


def _clean_section_title(text: str) -> str:
    value = _clean_title_candidate(text)
    value = re.sub(r"(章节|小节|部分|标题|题目)$", "", value).strip()
    return value


def _parse_chinese_number(token: str) -> int | None:
    token = str(token or "").strip()
    if not token:
        return None
    if token.isdigit():
        return int(token)
    mapping = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if token == "十":
        return 10
    if "十" in token:
        parts = token.split("十")
        total = 0
        total += mapping.get(parts[0], 1) * 10 if parts[0] else 10
        if len(parts) > 1 and parts[1]:
            total += mapping.get(parts[1], 0)
        return total if total > 0 else None
    return mapping.get(token)


def _split_title_list(raw: str) -> list[str]:
    value = str(raw or "").strip()
    if not value:
        return []
    for sep in [",", ";", " and ", " then ", " / ", "、", "，", "；"]:
        value = value.replace(sep, "|")
    parts = [p.strip() for p in value.split("|") if p.strip()]
    cleaned = [_clean_section_title(p) for p in parts]
    return [p for p in cleaned if p]


@dataclass
class EditOp:
    op: str
    args: dict


@dataclass
class RuleSpec:
    op: str
    regex: re.Pattern
    args: dict
    priority: int
    clean: list[str]
    clean_title: bool
    strip_quotes: list[str]
    types: dict
    detect_all: bool


_EDIT_RULES_CACHE: dict = {"mtime": 0.0, "rules": []}


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


def _parse_edit_ops_with_model(raw: str, text: str) -> list[EditOp]:
    _ = raw, text
    return []


def try_quick_edit(
    text: str,
    instruction: str,
    *,
    looks_like_modify_instruction,
) -> tuple[str, str] | None:
    raw = (instruction or "").strip()
    if not raw:
        return None
    ops = _parse_edit_ops(raw)
    if not ops and looks_like_modify_instruction(raw):
        ops = _parse_edit_ops_with_model(raw, text)
    if not ops:
        return None
    updated = _apply_edit_ops(text or "", ops)
    if updated.strip() != (text or "").strip():
        return updated, _build_quick_edit_note(ops)
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
) -> tuple[str, str] | None:
    if not _should_try_ai_edit(instruction, text, analysis, looks_like_modify_instruction=looks_like_modify_instruction):
        return None
    ops = _parse_edit_ops_with_model(instruction, text)
    if not ops:
        return None
    updated = _apply_edit_ops(text or "", ops)
    if updated.strip() != (text or "").strip():
        return updated, _build_quick_edit_note(ops)
    return None


def try_revision_edit(
    *,
    session,
    instruction: str,
    text: str,
    selection: str = "",
    analysis: dict | None = None,
    sanitize_output_text,
    replace_question_headings,
    get_ollama_settings_fn,
    ollama_client_cls,
) -> tuple[str, str] | None:
    _ = session
    raw = str(instruction or "").strip()
    base_text = str(text or "")
    if not raw or not base_text.strip():
        return None
    settings = get_ollama_settings_fn()
    if not settings.enabled:
        return None
    model = os.environ.get("WRITING_AGENT_REVISE_MODEL", "").strip() or settings.model
    client = ollama_client_cls(base_url=settings.base_url, model=model, timeout_s=settings.timeout_s)
    if not client.is_running():
        return None
    analysis_instruction = raw
    if isinstance(analysis, dict):
        analysis_instruction = str(analysis.get("rewritten_query") or raw).strip() or raw
    selection_text = str(selection or "").strip()
    if selection_text:
        system = (
            "你是文档修改助手，只改写“选中段落”。\n"
            "要求：\n"
            "1) 仅输出改写后的段落文本，不要输出标题或额外说明。\n"
            "2) 保持原意与结构，语言更清晰专业。\n"
            "3) 不新增事实、数据或引用；禁止占位符或自我指涉。\n"
        )
        user = (
            f"选中段落：\n{selection_text}\n\n"
            f"修改要求：\n{analysis_instruction}\n\n"
            "Please output the rewritten selected paragraph."
        )
    else:
        system = (
            "你是文档修改助手，需要按要求改写全文，但必须保持章节结构与顺序。\n"
            "要求：\n"
            "1) 仅输出纯文本，保留 # / ## / ### 标题行。\n"
            "2) 不删除正文段落（除非明显重复/乱码）；不改变章节顺序。\n"
            "3) 不编造事实、数据或引用；禁止占位符或自我指涉。\n"
            "4) 保留 [[TABLE:...]] / [[FIGURE:...]] 标记。\n"
        )
        user = (
            f"修改要求：\n{analysis_instruction}\n\n"
            f"原文：\n{base_text}\n\n"
            "Please output the rewritten full document."
        )
    buf: list[str] = []
    try:
        for delta in client.chat_stream(system=system, user=user, temperature=0.25):
            buf.append(delta)
    except Exception:
        return None
    rewritten = sanitize_output_text("".join(buf).strip())
    if not rewritten:
        return None
    if selection_text and selection_text in base_text:
        updated = base_text.replace(selection_text, rewritten, 1)
    else:
        updated = rewritten if not selection_text else base_text
    updated = replace_question_headings(updated)
    updated = sanitize_output_text(updated)
    if not updated.strip():
        return None
    return updated, "已按修改指令更新内容"
