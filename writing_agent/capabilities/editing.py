"""Editing capability helpers for inline and block edit workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PreparedInlineRequest:
    operation: Any
    context: Any
    kwargs: dict[str, Any]
    context_meta: dict[str, object]


def _clamp_int(value: int, lo: int, hi: int) -> int:
    return max(lo, min(hi, value))


def trim_inline_context(
    *,
    selected_text: str,
    before_text: str,
    after_text: str,
    policy: dict[str, object],
) -> tuple[str, str, dict[str, object]]:
    selected_len = len(str(selected_text or ""))
    base = int(policy.get("window_formula_base") or 220)
    coef = float(policy.get("window_formula_coef") or 0.8)
    extra = int(policy.get("short_selection_extra_chars") or 180)
    win_min = int(policy.get("window_min_chars") or 240)
    win_max = max(win_min, int(policy.get("window_max_chars") or 1200))
    short_threshold = int(policy.get("short_selection_threshold_chars") or 60)

    short_boost = extra if selected_len < short_threshold else 0
    side = _clamp_int(int(base + coef * max(1, selected_len) + short_boost), win_min, win_max)

    before_raw = str(before_text or "")
    after_raw = str(after_text or "")
    before_trim = before_raw[-side:] if len(before_raw) > side else before_raw
    after_trim = after_raw[:side] if len(after_raw) > side else after_raw
    trimmed_for_window = (before_trim != before_raw) or (after_trim != after_raw)
    reason_codes: list[str] = []
    if trimmed_for_window:
        reason_codes.append("context_window")

    total_cap = int(policy.get("context_total_max_chars") or 2400)
    if len(before_trim) + len(after_trim) > total_cap:
        half = max(120, total_cap // 2)
        before_trim = before_trim[-half:] if len(before_trim) > half else before_trim
        after_trim = after_trim[:half] if len(after_trim) > half else after_trim
        trimmed_for_window = True
        reason_codes.append("context_total_cap")

    meta = {
        "policy_version": str(policy.get("version") or "dynamic_v1"),
        "left_window_chars": int(len(before_trim)),
        "right_window_chars": int(len(after_trim)),
        "trimmed_for_budget": bool(trimmed_for_window),
        "truncate_reason_codes": reason_codes,
    }
    return before_trim, after_trim, meta


def prepare_inline_request(
    *,
    data: dict[str, Any],
    normalize_inline_context_policy_fn,
    trim_inline_context_fn,
    inline_operation_cls,
    inline_context_cls,
    tone_style_cls,
) -> PreparedInlineRequest:
    operation_raw = data.get("operation")
    selected_text = str(data.get("selected_text", "") or "")
    before_text_raw = str(data.get("before_text", "") or "")
    after_text_raw = str(data.get("after_text", "") or "")
    context_policy = normalize_inline_context_policy_fn(data.get("context_policy"))
    before_text, after_text, context_meta = trim_inline_context_fn(
        selected_text=selected_text,
        before_text=before_text_raw,
        after_text=after_text_raw,
        policy=context_policy,
    )

    try:
        operation = inline_operation_cls(operation_raw)
    except Exception as exc:
        raise ValueError(f"invalid operation: {operation_raw}") from exc

    context = inline_context_cls(
        selected_text=selected_text,
        before_text=before_text,
        after_text=after_text,
        document_title=data.get("document_title", ""),
        section_title=data.get("section_title"),
        document_type=data.get("document_type"),
        pretrimmed=True,
    )
    kwargs = build_inline_operation_kwargs(operation=operation, data=data, tone_style_cls=tone_style_cls)
    return PreparedInlineRequest(operation=operation, context=context, kwargs=kwargs, context_meta=context_meta)


def build_inline_operation_kwargs(*, operation: Any, data: dict[str, Any], tone_style_cls) -> dict[str, Any]:
    kwargs: dict[str, Any] = {}
    operation_value = str(getattr(operation, "value", operation) or "").strip().lower()

    if operation_value == "continue":
        kwargs["target_words"] = data.get("target_words", 200)
    elif operation_value == "improve":
        kwargs["focus"] = data.get("focus", "general")
    elif operation_value == "summarize":
        kwargs["max_sentences"] = data.get("max_sentences", 3)
    elif operation_value == "expand":
        kwargs["expansion_ratio"] = data.get("expansion_ratio", 2.0)
    elif operation_value == "change_tone":
        tone_str = data.get("target_tone", "professional")
        try:
            kwargs["target_tone"] = tone_style_cls(tone_str)
        except Exception:
            kwargs["target_tone"] = tone_style_cls.PROFESSIONAL
    elif operation_value == "ask_ai":
        kwargs["question"] = data.get("question", "")
    elif operation_value == "explain":
        kwargs["detail_level"] = data.get("detail_level", "medium")
    elif operation_value == "translate":
        kwargs["target_language"] = data.get("target_language", "en")

    return kwargs


def extract_block_text_from_ir(
    *,
    doc_ir_obj: Any,
    block_id: str,
    doc_ir_build_index_fn,
    doc_ir_render_block_text_fn,
) -> str:
    try:
        idx = doc_ir_build_index_fn(doc_ir_obj)
        block = idx.block_by_id.get(block_id)
        if block is None:
            return ""
        return str(doc_ir_render_block_text_fn(block) or "").strip()
    except Exception:
        return ""


def build_block_edit_variants(*, instruction: str, variants_raw: object, limit: int = 2) -> list[dict[str, str]]:
    variants: list[dict[str, str]] = []
    if isinstance(variants_raw, list):
        for item in variants_raw:
            if not isinstance(item, dict):
                continue
            label = str(item.get("label") or item.get("name") or "").strip()
            candidate_instruction = str(item.get("instruction") or "").strip()
            if candidate_instruction:
                variants.append(
                    {
                        "label": label or f"Variant {len(variants) + 1}",
                        "instruction": candidate_instruction,
                    }
                )
            if len(variants) >= limit:
                break

    if not variants:
        variants = [
            {"label": "Variant A", "instruction": instruction},
            {
                "label": "Variant B",
                "instruction": instruction + " Keep structure and maintain concise style.",
            },
        ]
    return variants[:limit]


def clone_doc_ir(*, doc_ir_obj: Any, doc_ir_to_dict_fn, doc_ir_from_dict_fn):
    return doc_ir_from_dict_fn(doc_ir_to_dict_fn(doc_ir_obj))


__all__ = [name for name in globals() if not name.startswith("__")]
