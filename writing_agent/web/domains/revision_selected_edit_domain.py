"""Revision edit selected-span and full-document revision helpers."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from writing_agent.web.domains import context_policy_domain
from writing_agent.web.domains.revision_edit_common_domain import (
    _coerce_int,
    _escape_prompt_text,
    _extract_json_block,
    _extract_tag_block,
    _inject_selected_revision_refine_failure,
    _record_selected_revision_metric,
)

@dataclass(frozen=True)
class _SelectionSpan:
    start: int
    end: int
    text: str
    source: str = "unknown"


@dataclass(frozen=True)
class _SelectedContextPackage:
    original: _SelectionSpan
    effective: _SelectionSpan
    left_context: str
    right_context: str
    left_window_chars: int
    right_window_chars: int
    trimmed_for_budget: bool
    budget_tokens: int
    policy_version: str


_MARKER_TOKEN_RE = re.compile(r"\[\[(?:TABLE|FIGURE):[\s\S]*?\]\]", flags=re.IGNORECASE)
_CONTEXT_TAG_OVERHEAD_TOKENS = 140


def _selection_text_from_payload(selection: object) -> str:
    if isinstance(selection, dict):
        return str(selection.get("text") or "")
    return str(selection or "")


def _resolve_selection_span(selection: object, base_text: str) -> _SelectionSpan | None:
    if isinstance(selection, dict):
        start = _coerce_int(selection.get("start"))
        end = _coerce_int(selection.get("end"))
        if start is not None and end is not None:
            start = max(0, min(len(base_text), int(start)))
            end = max(0, min(len(base_text), int(end)))
            if end > start:
                return _SelectionSpan(
                    start=start,
                    end=end,
                    text=base_text[start:end],
                    source="range",
                )
        selection = str(selection.get("text") or "")
    raw_text = str(selection or "")
    if not raw_text.strip():
        return None
    idx = base_text.find(raw_text)
    resolved = raw_text
    if idx < 0:
        compact = raw_text.strip()
        if compact and compact != raw_text:
            idx = base_text.find(compact)
            if idx >= 0:
                resolved = compact
    if idx < 0:
        return None
    return _SelectionSpan(
        start=idx,
        end=idx + len(resolved),
        text=base_text[idx : idx + len(resolved)],
        source="text_match",
    )


def _selection_anchor_matches(selection: object, base_text: str) -> bool:
    if not isinstance(selection, dict):
        return True
    start = _coerce_int(selection.get("start"))
    end = _coerce_int(selection.get("end"))
    expected = str(selection.get("text") or "")
    if not expected:
        return True
    if start is None or end is None:
        return True
    if start < 0 or end <= start or end > len(base_text):
        return False
    return base_text[start:end] == expected


def _clamp_int(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def _normalize_context_policy(raw: object) -> dict[str, object]:
    return context_policy_domain.normalize_selected_revision_context_policy(raw)


def _estimate_tokens(value: str) -> int:
    text = str(value or "")
    if not text:
        return 0
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    latin_words = len(re.findall(r"[A-Za-z0-9_]+", text))
    symbol_chars = len(re.findall(r"[^\sA-Za-z0-9_\u4e00-\u9fff]", text))
    return cjk + latin_words + int(symbol_chars * 0.5)


def _should_expand_selection(span: _SelectionSpan, policy: dict[str, object]) -> bool:
    short_chars = int(policy["short_selection_threshold_chars"])
    short_tokens = int(policy["short_selection_threshold_tokens"])
    return len(span.text) < short_chars or _estimate_tokens(span.text) < short_tokens


def _expand_to_sentence_bounds(base_text: str, start: int, end: int) -> tuple[int, int]:
    sentence_breaks = set(".!?;。！？；\n")
    left = start
    right = end
    while left > 0:
        if base_text[left - 1] in sentence_breaks:
            break
        left -= 1
    while left < start and left < len(base_text) and base_text[left].isspace():
        left += 1
    if right > 0 and base_text[right - 1] in sentence_breaks:
        return left, right
    while right < len(base_text):
        ch = base_text[right]
        right += 1
        if ch in sentence_breaks:
            break
    return left, right


def _expand_to_paragraph_bounds(base_text: str, start: int, end: int) -> tuple[int, int]:
    left = base_text.rfind("\n\n", 0, max(0, start))
    right = base_text.find("\n\n", min(len(base_text), end))
    left_idx = 0 if left < 0 else left + 2
    right_idx = len(base_text) if right < 0 else right
    return left_idx, right_idx


def _expand_effective_span(span: _SelectionSpan, base_text: str, policy: dict[str, object]) -> _SelectionSpan:
    if not _should_expand_selection(span, policy):
        return span
    s0, e0 = _expand_to_sentence_bounds(base_text, span.start, span.end)
    sentence_span = _SelectionSpan(start=s0, end=e0, text=base_text[s0:e0], source="sentence_expand")
    if not _should_expand_selection(sentence_span, policy):
        return sentence_span
    s1, e1 = _expand_to_paragraph_bounds(base_text, sentence_span.start, sentence_span.end)
    para_len = max(0, e1 - s1)
    sentence_len = max(1, len(sentence_span.text))
    # Avoid turning a tiny selection into whole-document replacement when no real paragraph boundary exists.
    if (s1 <= 0 and e1 >= len(base_text)) or para_len > max(1200, sentence_len * 4):
        return sentence_span
    return _SelectionSpan(start=s1, end=e1, text=base_text[s1:e1], source="paragraph_expand")


def _compute_context_windows(
    *,
    instruction: str,
    effective_len: int,
    policy: dict[str, object],
) -> tuple[int, int]:
    base = int(policy["window_formula_base"])
    coef = float(policy["window_formula_coef"])
    short_boost = int(policy["short_boost_chars"]) if effective_len < int(policy["short_boost_threshold_chars"]) else 0
    side = int(round(base + coef * effective_len + short_boost))
    win_min = int(policy["window_min_chars"])
    win_max = max(win_min, int(policy["window_max_chars"]))
    side = _clamp_int(side, win_min, win_max)
    compact = re.sub(r"\s+", "", str(instruction or "")).lower()
    left_mult = 1.0
    right_mult = 1.0
    if re.search(r"(续写|承接上文|延续前文|continue|carryon|buildon)", compact):
        left_mult, right_mult = 1.2, 0.8
    elif re.search(r"(引出下文|过渡到下文|衔接后文|leadintone|transitionto)", compact):
        left_mult, right_mult = 0.8, 1.2
    left = _clamp_int(int(round(side * left_mult)), win_min, win_max)
    right = _clamp_int(int(round(side * right_mult)), win_min, win_max)
    return left, right


def _estimate_selected_prompt_tokens(
    *,
    instruction: str,
    left_context: str,
    selected_text: str,
    right_context: str,
) -> int:
    return (
        _CONTEXT_TAG_OVERHEAD_TOKENS
        + _estimate_tokens(instruction)
        + _estimate_tokens(left_context)
        + _estimate_tokens(selected_text)
        + _estimate_tokens(right_context)
    )


def _build_selected_context_package(
    *,
    base_text: str,
    instruction: str,
    original: _SelectionSpan,
    policy: dict[str, object],
) -> tuple[_SelectedContextPackage | None, str]:
    effective = _expand_effective_span(original, base_text, policy)
    effective_len = max(1, effective.end - effective.start)
    left_window, right_window = _compute_context_windows(
        instruction=instruction,
        effective_len=effective_len,
        policy=policy,
    )
    win_min = int(policy["window_min_chars"])
    win_max = int(policy["window_max_chars"])
    min_after_trim = int(policy["min_window_after_trim_chars"])
    prompt_budget_tokens = max(
        256,
        int(float(policy["prompt_context_tokens"]) * float(policy["prompt_budget_ratio"])),
    )
    trimmed = False
    loops = 0
    while loops < 8:
        loops += 1
        left_window = _clamp_int(left_window, 0, win_max)
        right_window = _clamp_int(right_window, 0, win_max)
        left_start = max(0, effective.start - left_window)
        right_end = min(len(base_text), effective.end + right_window)
        left_context = base_text[left_start:effective.start]
        right_context = base_text[effective.end:right_end]
        est = _estimate_selected_prompt_tokens(
            instruction=instruction,
            left_context=left_context,
            selected_text=effective.text,
            right_context=right_context,
        )
        if est <= prompt_budget_tokens:
            return (
                _SelectedContextPackage(
                    original=original,
                    effective=effective,
                    left_context=left_context,
                    right_context=right_context,
                    left_window_chars=left_window,
                    right_window_chars=right_window,
                    trimmed_for_budget=trimmed,
                    budget_tokens=prompt_budget_tokens,
                    policy_version=str(policy.get("version") or "dynamic_v1"),
                ),
                "",
            )
        trimmed = True
        ratio = prompt_budget_tokens / max(est, 1)
        next_left = int(left_window * max(0.4, ratio))
        next_right = int(right_window * max(0.4, ratio))
        if left_window > min_after_trim:
            next_left = max(min_after_trim, next_left)
        if right_window > min_after_trim:
            next_right = max(min_after_trim, next_right)
        if next_left == left_window and left_window > min_after_trim:
            next_left = max(min_after_trim, left_window - 80)
        if next_right == right_window and right_window > min_after_trim:
            next_right = max(min_after_trim, right_window - 80)
        left_window = _clamp_int(next_left, 0, win_max)
        right_window = _clamp_int(next_right, 0, win_max)
    if min_after_trim < win_min:
        left_window = min(left_window, min_after_trim)
        right_window = min(right_window, min_after_trim)
    left_start = max(0, effective.start - left_window)
    right_end = min(len(base_text), effective.end + right_window)
    left_context = base_text[left_start:effective.start]
    right_context = base_text[effective.end:right_end]
    est = _estimate_selected_prompt_tokens(
        instruction=instruction,
        left_context=left_context,
        selected_text=effective.text,
        right_context=right_context,
    )
    if est <= prompt_budget_tokens:
        return (
            _SelectedContextPackage(
                original=original,
                effective=effective,
                left_context=left_context,
                right_context=right_context,
                left_window_chars=left_window,
                right_window_chars=right_window,
                trimmed_for_budget=True,
                budget_tokens=prompt_budget_tokens,
                policy_version=str(policy.get("version") or "dynamic_v1"),
            ),
            "",
        )
    left_context = ""
    right_context = ""
    est = _estimate_selected_prompt_tokens(
        instruction=instruction,
        left_context=left_context,
        selected_text=effective.text,
        right_context=right_context,
    )
    if est <= prompt_budget_tokens:
        return (
            _SelectedContextPackage(
                original=original,
                effective=effective,
                left_context=left_context,
                right_context=right_context,
                left_window_chars=0,
                right_window_chars=0,
                trimmed_for_budget=True,
                budget_tokens=prompt_budget_tokens,
                policy_version=str(policy.get("version") or "dynamic_v1"),
            ),
            "",
        )
    return None, "E_BUDGET_EXCEEDED"


def _build_selected_revision_prompts(
    *,
    instruction: str,
    package: _SelectedContextPackage,
    expected_hash: str,
    refine_reason: str = "",
) -> tuple[str, str]:
    escaped_instruction = _escape_prompt_text(instruction)
    escaped_hash = _escape_prompt_text(expected_hash)
    escaped_left = _escape_prompt_text(package.left_context)
    escaped_selected = _escape_prompt_text(package.effective.text)
    escaped_right = _escape_prompt_text(package.right_context)
    escaped_policy = _escape_prompt_text(package.policy_version)
    refine_hint = ""
    if refine_reason:
        refine_hint = (
            "\n<failure_context>\n"
            f"{_escape_prompt_text(refine_reason)}\n"
            "</failure_context>\n"
        )
    system = (
        "You are a controlled text editor.\n"
        "Edit only <selected_text>. Treat <left_context> and <right_context> as read-only references.\n"
        "Return only JSON and no markdown fences.\n"
        "Schema:\n"
        "{"
        '"ops":[{"op":"replace","value":"..."}],'
        '"meta":{"risk_level":"low|medium|high","notes":"..."},'
        '"checks":{"preserve_markers":true}'
        "}\n"
        "Rules:\n"
        "1) Keep edits local and minimal.\n"
        "2) Preserve factual meaning.\n"
        "3) Preserve marker tokens like [[TABLE:...]] and [[FIGURE:...]] when present.\n"
    )
    user = (
        "<task>rewrite_selected_text</task>\n"
        f"<instruction>{escaped_instruction}</instruction>\n"
        "<constraints>\n"
        "Only modify selected_text. Do not alter text outside selected_text.\n"
        "Do not introduce placeholders.\n"
        "Return valid JSON with exactly one replace operation.\n"
        "</constraints>\n"
        f"<preconditions><test_hash>{escaped_hash}</test_hash></preconditions>\n"
        f"<left_context>{escaped_left}</left_context>\n"
        f"<selected_text>{escaped_selected}</selected_text>\n"
        f"<right_context>{escaped_right}</right_context>\n"
        f"<policy_version>{escaped_policy}</policy_version>\n"
        f"{refine_hint}"
    )
    return system, user


def _build_full_document_revision_prompts(
    *,
    instruction: str,
    base_text: str,
    retry_reason: str = "",
) -> tuple[str, str]:
    escaped_instruction = _escape_prompt_text(instruction)
    escaped_text = _escape_prompt_text(base_text)
    retry_block = ""
    if retry_reason:
        retry_block = (
            "<retry_reason>\n"
            f"{_escape_prompt_text(retry_reason)}\n"
            "</retry_reason>\n"
        )
    system = (
        "You are a constrained full-document revision assistant.\n"
        "Output revised markdown only inside <revised_document>...</revised_document>.\n"
        "Do not output analysis, markdown fences, or text outside that block."
    )
    user = (
        "<task>revise_full_document</task>\n"
        "<constraints>\n"
        "- Keep heading structure and order unless instruction explicitly asks to change it.\n"
        "- Preserve markers like [[TABLE:...]] and [[FIGURE:...]].\n"
        "- Do not fabricate facts, numbers, references, or placeholders.\n"
        "- Treat tagged blocks as separate channels.\n"
        "</constraints>\n"
        f"<user_requirement>\n{escaped_instruction}\n</user_requirement>\n"
        f"<original_document>\n{escaped_text}\n</original_document>\n"
        f"{retry_block}"
        "Return exactly one block:\n"
        "<revised_document>\n"
        "...full revised markdown...\n"
        "</revised_document>\n"
    )
    return system, user


def _chat_once(client: Any, *, system: str, user: str, temperature: float) -> str:
    if hasattr(client, "chat") and callable(getattr(client, "chat")):
        return str(client.chat(system=system, user=user, temperature=temperature) or "")
    if hasattr(client, "chat_stream") and callable(getattr(client, "chat_stream")):
        buf: list[str] = []
        for delta in client.chat_stream(system=system, user=user, temperature=temperature):
            buf.append(str(delta))
        return "".join(buf)
    raise RuntimeError("llm client missing chat/chat_stream")


def _emit_revision_status(report_status: Callable[[dict[str, Any]], None] | None, payload: dict[str, Any]) -> None:
    if not callable(report_status):
        return
    try:
        report_status(dict(payload))
    except Exception:
        return


def _extract_rewrite_from_response(raw_output: str, *, sanitize_output_text) -> tuple[str, str]:
    raw_json = _extract_json_block(raw_output)
    payload: Any = None
    if raw_json:
        try:
            payload = json.loads(raw_json)
        except Exception:
            payload = None
    if isinstance(payload, dict):
        ops = payload.get("ops")
        if isinstance(ops, list):
            for item in ops:
                if not isinstance(item, dict):
                    continue
                kind = str(item.get("op") or "").strip().lower()
                if kind != "replace":
                    continue
                value = item.get("value")
                if isinstance(value, str):
                    rewritten = sanitize_output_text(value).strip()
                    if rewritten:
                        return rewritten, ""
        direct = payload.get("rewritten_text")
        if isinstance(direct, str):
            rewritten = sanitize_output_text(direct).strip()
            if rewritten:
                return rewritten, ""
        return "", "E_SCHEMA_INVALID"
    allow_plain_text = os.environ.get("WRITING_AGENT_REVISE_ALLOW_PLAIN_TEXT", "1").strip().lower() not in {"0", "false", "no", "off"}
    if allow_plain_text:
        fallback = sanitize_output_text(raw_output).strip()
        if fallback:
            return fallback, ""
    return "", "E_SCHEMA_INVALID"


def _marker_fingerprint(text: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for match in _MARKER_TOKEN_RE.finditer(str(text or "")):
        token = match.group(0)
        out[token] = int(out.get(token, 0)) + 1
    return out


def _apply_atomic_replace(base_text: str, span: _SelectionSpan, rewritten: str) -> tuple[str, str]:
    expected_hash = sha256(base_text[span.start : span.end].encode("utf-8")).hexdigest()
    current_hash = sha256(base_text[span.start : span.end].encode("utf-8")).hexdigest()
    if current_hash != expected_hash:
        return "", "E_ANCHOR_MISMATCH"
    updated = base_text[: span.start] + rewritten + base_text[span.end :]
    if updated[: span.start] != base_text[: span.start]:
        return "", "E_OFFTARGET_EDIT"
    if updated[span.start + len(rewritten) :] != base_text[span.end :]:
        return "", "E_OFFTARGET_EDIT"
    return updated, ""


def try_revision_edit(
    *,
    session,
    instruction: str,
    text: str,
    selection: object = "",
    analysis: dict | None = None,
    context_policy: object | None = None,
    report_status: Callable[[dict[str, Any]], None] | None = None,
    sanitize_output_text,
    replace_question_headings,
    get_ollama_settings_fn,
    ollama_client_cls,
) -> tuple[str, str] | None:
    _ = session
    raw = str(instruction or "").strip()
    base_text = str(text or "")
    if not raw or not base_text.strip():
        _emit_revision_status(report_status, {"ok": False, "error_code": "E_EMPTY_INPUT"})
        return None
    settings = get_ollama_settings_fn()
    if not settings.enabled:
        _emit_revision_status(report_status, {"ok": False, "error_code": "E_MODEL_DISABLED"})
        return None
    model = os.environ.get("WRITING_AGENT_REVISE_MODEL", "").strip() or settings.model
    client = ollama_client_cls(base_url=settings.base_url, model=model, timeout_s=settings.timeout_s)
    if not client.is_running():
        _emit_revision_status(report_status, {"ok": False, "error_code": "E_MODEL_UNAVAILABLE"})
        return None
    analysis_instruction = raw
    if isinstance(analysis, dict):
        analysis_instruction = str(analysis.get("rewritten_query") or raw).strip() or raw

    selection_span = _resolve_selection_span(selection, base_text)
    if selection_span is not None:
        selection_source = str(selection_span.source or "unknown")
        if not _selection_anchor_matches(selection, base_text):
            _record_selected_revision_metric(
                "apply_failed",
                instruction=analysis_instruction,
                selection_source=selection_source,
                error_code="E_ANCHOR_MISMATCH",
            )
            _emit_revision_status(
                report_status,
                {"ok": False, "error_code": "E_ANCHOR_MISMATCH", "selection_source": selection_source},
            )
            return None
        policy = _normalize_context_policy(context_policy)
        package, package_error = _build_selected_context_package(
            base_text=base_text,
            instruction=analysis_instruction,
            original=selection_span,
            policy=policy,
        )
        if package is None:
            code = str(package_error or "E_BUDGET_EXCEEDED")
            _record_selected_revision_metric(
                "package_failed",
                instruction=analysis_instruction,
                selection_source=selection_source,
                policy_version=str(policy.get("version") or "dynamic_v1"),
                error_code=code,
                original_len=max(0, selection_span.end - selection_span.start),
            )
            _emit_revision_status(
                report_status,
                {
                    "ok": False,
                    "error_code": code,
                    "selection_source": selection_source,
                    "policy_version": str(policy.get("version") or "dynamic_v1"),
                },
            )
            return None
        pre_hash = sha256(package.effective.text.encode("utf-8")).hexdigest()
        _record_selected_revision_metric(
            "package_ready",
            instruction=analysis_instruction,
            selection_source=selection_source,
            policy_version=package.policy_version,
            trimmed_for_budget=package.trimmed_for_budget,
            original_len=max(0, package.original.end - package.original.start),
            effective_len=max(0, package.effective.end - package.effective.start),
            left_window_chars=package.left_window_chars,
            right_window_chars=package.right_window_chars,
        )
        refine_triggered = False
        refine_recovered = False
        try:
            system, user = _build_selected_revision_prompts(
                instruction=analysis_instruction,
                package=package,
                expected_hash=pre_hash,
            )
            raw_out = _chat_once(client, system=system, user=user, temperature=0.2)
            rewritten, parse_error = _extract_rewrite_from_response(raw_out, sanitize_output_text=sanitize_output_text)
            if parse_error:
                refine_triggered = True
                _record_selected_revision_metric(
                    "fallback_triggered",
                    instruction=analysis_instruction,
                    selection_source=selection_source,
                    policy_version=package.policy_version,
                    error_code=parse_error,
                    fallback_triggered=True,
                    trimmed_for_budget=package.trimmed_for_budget,
                )
                refine_system, refine_user = _build_selected_revision_prompts(
                    instruction=analysis_instruction,
                    package=package,
                    expected_hash=pre_hash,
                    refine_reason=parse_error,
                )
                raw_out = _chat_once(client, system=refine_system, user=refine_user, temperature=0.15)
                rewritten, parse_error = _extract_rewrite_from_response(raw_out, sanitize_output_text=sanitize_output_text)
                if _inject_selected_revision_refine_failure():
                    parse_error = "E_INJECTED_REFINE_FAILURE"
                if parse_error:
                    _record_selected_revision_metric(
                        "fallback_failed",
                        instruction=analysis_instruction,
                        selection_source=selection_source,
                        policy_version=package.policy_version,
                        error_code="E_REFINE_FAILED",
                        fallback_triggered=True,
                        fallback_recovered=False,
                        trimmed_for_budget=package.trimmed_for_budget,
                    )
                    _emit_revision_status(
                        report_status,
                        {
                            "ok": False,
                            "error_code": "E_REFINE_FAILED",
                            "selection_source": selection_source,
                            "policy_version": package.policy_version,
                            "fallback_triggered": True,
                            "fallback_recovered": False,
                        },
                    )
                    return None
                refine_recovered = True
                _record_selected_revision_metric(
                    "fallback_recovered",
                    instruction=analysis_instruction,
                    selection_source=selection_source,
                    policy_version=package.policy_version,
                    fallback_triggered=True,
                    fallback_recovered=True,
                    trimmed_for_budget=package.trimmed_for_budget,
                )
        except Exception:
            _record_selected_revision_metric(
                "model_failed",
                instruction=analysis_instruction,
                selection_source=selection_source,
                policy_version=package.policy_version,
                error_code="E_MODEL_RUNTIME",
                fallback_triggered=refine_triggered,
                fallback_recovered=refine_recovered,
                trimmed_for_budget=package.trimmed_for_budget,
            )
            _emit_revision_status(
                report_status,
                {
                    "ok": False,
                    "error_code": "E_MODEL_RUNTIME",
                    "selection_source": selection_source,
                    "policy_version": package.policy_version,
                    "fallback_triggered": refine_triggered,
                    "fallback_recovered": refine_recovered,
                },
            )
            return None
        rewritten = replace_question_headings(sanitize_output_text(rewritten).strip())
        if not rewritten:
            _record_selected_revision_metric(
                "apply_failed",
                instruction=analysis_instruction,
                selection_source=selection_source,
                policy_version=package.policy_version,
                error_code="E_SCHEMA_INVALID",
                fallback_triggered=refine_triggered,
                fallback_recovered=refine_recovered,
                trimmed_for_budget=package.trimmed_for_budget,
            )
            _emit_revision_status(
                report_status,
                {
                    "ok": False,
                    "error_code": "E_SCHEMA_INVALID",
                    "selection_source": selection_source,
                    "policy_version": package.policy_version,
                    "fallback_triggered": refine_triggered,
                    "fallback_recovered": refine_recovered,
                },
            )
            return None
        before_marker_fp = _marker_fingerprint(base_text)
        updated, apply_error = _apply_atomic_replace(base_text, package.effective, rewritten)
        if apply_error:
            _record_selected_revision_metric(
                "apply_failed",
                instruction=analysis_instruction,
                selection_source=selection_source,
                policy_version=package.policy_version,
                error_code=apply_error,
                fallback_triggered=refine_triggered,
                fallback_recovered=refine_recovered,
                trimmed_for_budget=package.trimmed_for_budget,
            )
            _emit_revision_status(
                report_status,
                {
                    "ok": False,
                    "error_code": apply_error,
                    "selection_source": selection_source,
                    "policy_version": package.policy_version,
                    "fallback_triggered": refine_triggered,
                    "fallback_recovered": refine_recovered,
                },
            )
            return None
        if before_marker_fp != _marker_fingerprint(updated):
            _record_selected_revision_metric(
                "apply_failed",
                instruction=analysis_instruction,
                selection_source=selection_source,
                policy_version=package.policy_version,
                error_code="E_MARKER_BROKEN",
                fallback_triggered=refine_triggered,
                fallback_recovered=refine_recovered,
                trimmed_for_budget=package.trimmed_for_budget,
            )
            _emit_revision_status(
                report_status,
                {
                    "ok": False,
                    "error_code": "E_MARKER_BROKEN",
                    "selection_source": selection_source,
                    "policy_version": package.policy_version,
                    "fallback_triggered": refine_triggered,
                    "fallback_recovered": refine_recovered,
                },
            )
            return None
        if not updated.strip():
            _record_selected_revision_metric(
                "apply_failed",
                instruction=analysis_instruction,
                selection_source=selection_source,
                policy_version=package.policy_version,
                error_code="E_SCHEMA_INVALID",
                fallback_triggered=refine_triggered,
                fallback_recovered=refine_recovered,
                trimmed_for_budget=package.trimmed_for_budget,
            )
            _emit_revision_status(
                report_status,
                {
                    "ok": False,
                    "error_code": "E_SCHEMA_INVALID",
                    "selection_source": selection_source,
                    "policy_version": package.policy_version,
                    "fallback_triggered": refine_triggered,
                    "fallback_recovered": refine_recovered,
                },
            )
            return None
        note = (
            "selected revision applied "
            f"[policy={package.policy_version};window={package.left_window_chars}/{package.right_window_chars};"
            f"trimmed={int(package.trimmed_for_budget)}]"
        )
        _record_selected_revision_metric(
            "apply_success",
            instruction=analysis_instruction,
            selection_source=selection_source,
            policy_version=package.policy_version,
            trimmed_for_budget=package.trimmed_for_budget,
            fallback_triggered=refine_triggered,
            fallback_recovered=refine_recovered,
            original_len=max(0, package.original.end - package.original.start),
            effective_len=max(0, package.effective.end - package.effective.start),
            left_window_chars=package.left_window_chars,
            right_window_chars=package.right_window_chars,
        )
        _emit_revision_status(
            report_status,
            {
                "ok": True,
                "error_code": "",
                "selection_source": selection_source,
                "policy_version": package.policy_version,
                "trimmed_for_budget": bool(package.trimmed_for_budget),
                "fallback_triggered": refine_triggered,
                "fallback_recovered": refine_recovered,
                "left_window_chars": int(package.left_window_chars),
                "right_window_chars": int(package.right_window_chars),
                "original_len": int(max(0, package.original.end - package.original.start)),
                "effective_len": int(max(0, package.effective.end - package.effective.start)),
            },
        )
        return updated, note

    if _selection_text_from_payload(selection).strip():
        _record_selected_revision_metric(
            "selection_unresolved",
            instruction=analysis_instruction,
            selection_source="text_payload",
            error_code="E_ANCHOR_MISMATCH",
        )
        _emit_revision_status(report_status, {"ok": False, "error_code": "E_ANCHOR_MISMATCH"})
        return None

    system, user = _build_full_document_revision_prompts(
        instruction=analysis_instruction,
        base_text=base_text,
    )
    buf: list[str] = []
    try:
        for delta in client.chat_stream(system=system, user=user, temperature=0.25):
            buf.append(delta)
    except Exception:
        return None
    raw_out = "".join(buf).strip()
    rewritten = _extract_tag_block(raw_out, "revised_document")
    if not rewritten:
        retry_system, retry_user = _build_full_document_revision_prompts(
            instruction=analysis_instruction,
            base_text=base_text,
            retry_reason="Previous output missed required <revised_document> wrapper.",
        )
        retry_buf: list[str] = []
        try:
            for delta in client.chat_stream(system=retry_system, user=retry_user, temperature=0.15):
                retry_buf.append(delta)
        except Exception:
            return None
        rewritten = _extract_tag_block("".join(retry_buf).strip(), "revised_document")
    rewritten = sanitize_output_text(rewritten or "")
    if not rewritten:
        _emit_revision_status(report_status, {"ok": False, "error_code": "E_SCHEMA_INVALID"})
        return None
    if rewritten.strip().lower() == analysis_instruction.strip().lower():
        _emit_revision_status(report_status, {"ok": False, "error_code": "E_SCHEMA_INVALID"})
        return None
    updated = replace_question_headings(rewritten)
    updated = sanitize_output_text(updated)
    if not updated.strip():
        _emit_revision_status(report_status, {"ok": False, "error_code": "E_SCHEMA_INVALID"})
        return None
    _emit_revision_status(report_status, {"ok": True, "error_code": "", "selection_source": "full_document"})
    return updated, "revision applied (full_document)"


__all__ = [
    name
    for name in globals()
    if not name.startswith("__")
    and name not in {
        "os",
        "re",
        "dataclass",
        "sha256",
        "Any",
        "Callable",
        "context_policy_domain",
        "_clean_title_candidate",
        "_coerce_int",
        "_collect_section_titles",
        "_escape_prompt_text",
        "_extract_tag_block",
        "_inject_selected_revision_refine_failure",
        "_normalize_heading_text",
        "_record_selected_revision_metric",
    }
]
