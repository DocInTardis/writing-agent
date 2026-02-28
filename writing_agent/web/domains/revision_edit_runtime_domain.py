"""Revision Edit Runtime Domain module.

This module belongs to `writing_agent.web.domains` in the writing-agent codebase.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from hashlib import sha256
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

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

_ALLOWED_EDIT_OPS = {
    "set_title",
    "replace_text",
    "rename_section",
    "add_section",
    "delete_section",
    "move_section",
    "replace_section_content",
    "append_section_content",
    "merge_sections",
    "swap_sections",
    "split_section",
    "reorder_sections",
}
_LOW_RISK_OPS = {"set_title", "replace_text"}
_MEDIUM_RISK_OPS = {"rename_section", "add_section", "move_section", "replace_section_content", "append_section_content"}
_HIGH_RISK_OPS = {"delete_section", "merge_sections", "swap_sections", "split_section", "reorder_sections"}
_CONFIRM_TOKENS_RE = re.compile(
    r"(?:\u786e\u8ba4\u6267\u884c|\u7ee7\u7eed\u6267\u884c|\u7acb\u5373\u6267\u884c|\u5f3a\u5236\u6267\u884c|confirm\s*apply|force\s*apply)",
    flags=re.IGNORECASE,
)
_EDIT_PLAN_METRICS_LOCK = threading.Lock()


@dataclass
class EditPlanV2:
    operations: list[EditOp] = field(default_factory=list)
    version: str = "v2"
    confidence: float = 0.0
    ambiguities: list[str] = field(default_factory=list)
    requires_confirmation: bool = False
    risk_level: str = "low"
    source: str = "rules"


@dataclass
class EditExecutionResult:
    text: str
    note: str
    applied: bool = False
    requires_confirmation: bool = False
    confirmation_reason: str = ""
    risk_level: str = "low"
    source: str = "rules"
    confidence: float = 0.0
    operations_count: int = 0


def _edit_plan_metrics_enabled() -> bool:
    raw = os.environ.get("WRITING_AGENT_EDIT_PLAN_METRICS_ENABLE", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _edit_plan_metrics_path() -> Path:
    raw = os.environ.get("WRITING_AGENT_EDIT_PLAN_METRICS_PATH", "").strip()
    if raw:
        return Path(raw)
    return Path(".data/metrics/edit_plan_events.jsonl")


def _edit_plan_metrics_max_bytes() -> int:
    raw = os.environ.get("WRITING_AGENT_EDIT_PLAN_METRICS_MAX_BYTES", "2097152").strip()
    try:
        value = int(float(raw))
    except Exception:
        value = 2097152
    return max(262144, value)


def _trim_metrics_file_locked(path: Path, max_bytes: int) -> None:
    try:
        if not path.exists():
            return
        size = path.stat().st_size
    except Exception:
        return
    if size <= max_bytes:
        return
    try:
        raw = path.read_bytes()
    except Exception:
        return
    if len(raw) <= max_bytes:
        return
    tail = raw[-max_bytes:]
    # Keep complete lines to avoid broken JSON rows.
    first_nl = tail.find(b"\n")
    if first_nl >= 0 and first_nl + 1 < len(tail):
        tail = tail[first_nl + 1 :]
    try:
        path.write_bytes(tail)
    except Exception:
        return


def _request_fingerprint(raw: str) -> str:
    value = _normalize_edit_instruction_text(raw)
    if not value:
        return ""
    try:
        return sha256(value.encode("utf-8")).hexdigest()[:16]
    except Exception:
        return ""


def _record_edit_plan_metric(
    event: str,
    *,
    raw: str,
    prefer_model: bool,
    fallback_used: bool,
    plan: EditPlanV2 | None = None,
    executed: bool | None = None,
    blocked_reason: str = "",
    parse_ok: bool | None = None,
) -> None:
    if not _edit_plan_metrics_enabled():
        return
    row: dict[str, Any] = {
        "ts": round(time.time(), 3),
        "event": str(event or "").strip() or "unknown",
        "request_fp": _request_fingerprint(raw),
        "prefer_model": bool(prefer_model),
        "fallback_used": bool(fallback_used),
    }
    if parse_ok is not None:
        row["parse_ok"] = bool(parse_ok)
    if executed is not None:
        row["executed"] = bool(executed)
    if blocked_reason:
        row["blocked_reason"] = str(blocked_reason)
    if plan is not None:
        row.update(
            {
                "source": plan.source,
                "risk_level": plan.risk_level,
                "requires_confirmation": bool(plan.requires_confirmation),
                "operations_count": len(plan.operations),
                "confidence": round(float(plan.confidence or 0.0), 4),
            }
        )
    path = _edit_plan_metrics_path()
    line = json.dumps(row, ensure_ascii=False) + "\n"
    with _EDIT_PLAN_METRICS_LOCK:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            _trim_metrics_file_locked(path, _edit_plan_metrics_max_bytes())
            with path.open("a", encoding="utf-8") as f:
                f.write(line)
            _trim_metrics_file_locked(path, _edit_plan_metrics_max_bytes())
        except Exception:
            return


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


def _extract_json_block(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-zA-Z0-9_-]*", "", raw).strip().strip("`").strip()
    if raw.startswith("{") and raw.endswith("}"):
        return raw
    match = re.search(r"\{[\s\S]*\}", raw)
    if not match:
        return ""
    return match.group(0).strip()


def _coerce_int(value: object) -> int | None:
    try:
        return int(float(value))
    except Exception:
        return None


def _collect_section_titles(text: str) -> list[str]:
    titles: list[str] = []
    for line in str(text or "").replace("\r", "").split("\n"):
        m = re.match(r"^\s*#{1,6}\s+(.+?)\s*$", line)
        if not m:
            continue
        title = _clean_section_title(m.group(1))
        if title:
            titles.append(title)
    # keep order, drop duplicates
    seen: set[str] = set()
    out: list[str] = []
    for item in titles:
        key = _normalize_heading_text(item)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _risk_level_from_ops(ops: list[EditOp]) -> str:
    if not ops:
        return "low"
    for op in ops:
        if op.op == "replace_text" and bool((op.args or {}).get("all")):
            return "high"
        if op.op in _HIGH_RISK_OPS:
            return "high"
    if len(ops) >= 4:
        return "high"
    if any(op.op in _MEDIUM_RISK_OPS for op in ops) or len(ops) >= 2:
        return "medium"
    return "low"


def _requires_confirmation(risk_level: str) -> bool:
    enabled = os.environ.get("WRITING_AGENT_EDIT_REQUIRE_CONFIRM_HIGH", "1").strip().lower() not in {"0", "false", "no", "off"}
    return enabled and risk_level == "high"


def _has_confirmation_token(raw: str) -> bool:
    return bool(_CONFIRM_TOKENS_RE.search(str(raw or "")))


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
        f"Instruction:\n{raw}\n\n"
        f"Known headings:\n{heading_hint}\n\n"
        "Return only valid JSON following schema."
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
