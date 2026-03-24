"""Revision edit shared types, metrics, and prompt helpers."""

from __future__ import annotations

import json
import os
import re
import threading
import time
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable

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
    value = re.sub(r"\s+", " ", str(raw or "").strip())
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


def _selected_revision_metrics_enabled() -> bool:
    raw = os.environ.get("WRITING_AGENT_SELECTED_REVISION_METRICS_ENABLE", "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _selected_revision_metrics_path() -> Path:
    raw = os.environ.get("WRITING_AGENT_SELECTED_REVISION_METRICS_PATH", "").strip()
    if raw:
        return Path(raw)
    return Path(".data/metrics/selected_revision_events.jsonl")


def _selected_revision_metrics_max_bytes() -> int:
    raw = os.environ.get("WRITING_AGENT_SELECTED_REVISION_METRICS_MAX_BYTES", "2097152").strip()
    try:
        value = int(float(raw))
    except Exception:
        value = 2097152
    return max(262144, value)


def _inject_selected_revision_refine_failure() -> bool:
    raw = os.environ.get("WRITING_AGENT_FAIL_INJECT_SELECTED_REVISION_REFINE", "0").strip().lower()
    return raw not in {"", "0", "false", "no", "off"}


def _record_selected_revision_metric(
    event: str,
    *,
    instruction: str,
    selection_source: str = "",
    policy_version: str = "",
    error_code: str = "",
    trimmed_for_budget: bool | None = None,
    fallback_triggered: bool | None = None,
    fallback_recovered: bool | None = None,
    original_len: int | None = None,
    effective_len: int | None = None,
    left_window_chars: int | None = None,
    right_window_chars: int | None = None,
) -> None:
    if not _selected_revision_metrics_enabled():
        return
    row: dict[str, Any] = {
        "ts": round(time.time(), 3),
        "event": str(event or "").strip() or "unknown",
        "request_fp": _request_fingerprint(instruction),
    }
    if selection_source:
        row["selection_source"] = str(selection_source)
    if policy_version:
        row["policy_version"] = str(policy_version)
    if error_code:
        row["error_code"] = str(error_code)
    if trimmed_for_budget is not None:
        row["trimmed_for_budget"] = bool(trimmed_for_budget)
    if fallback_triggered is not None:
        row["fallback_triggered"] = bool(fallback_triggered)
    if fallback_recovered is not None:
        row["fallback_recovered"] = bool(fallback_recovered)
    if original_len is not None:
        row["original_len"] = int(max(0, original_len))
    if effective_len is not None:
        row["effective_len"] = int(max(0, effective_len))
    if left_window_chars is not None:
        row["left_window_chars"] = int(max(0, left_window_chars))
    if right_window_chars is not None:
        row["right_window_chars"] = int(max(0, right_window_chars))
    path = _selected_revision_metrics_path()
    line = json.dumps(row, ensure_ascii=False) + "\n"
    with _EDIT_PLAN_METRICS_LOCK:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            _trim_metrics_file_locked(path, _selected_revision_metrics_max_bytes())
            with path.open("a", encoding="utf-8") as f:
                f.write(line)
            _trim_metrics_file_locked(path, _selected_revision_metrics_max_bytes())
        except Exception:
            return

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


def _escape_prompt_text(raw: object) -> str:
    text = str(raw or "")
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _extract_tag_block(text: str, tag: str) -> str:
    raw = str(text or "")
    key = str(tag or "").strip().lower()
    if not key:
        return ""
    pattern = rf"<{re.escape(key)}>\s*([\s\S]*?)\s*</{re.escape(key)}>"
    match = re.search(pattern, raw, flags=re.IGNORECASE)
    if not match:
        return ""
    return str(match.group(1) or "").strip()


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


__all__ = [
    name
    for name in globals()
    if not name.startswith("__")
    and name not in {
        "json",
        "os",
        "re",
        "threading",
        "time",
        "sha256",
        "dataclass",
        "field",
        "Path",
        "Any",
        "Callable",
    }
]
