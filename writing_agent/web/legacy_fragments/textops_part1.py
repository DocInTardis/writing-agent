"""Legacy text operation helpers: preference clarification questions."""

from __future__ import annotations

import json
import math
import re
from typing import Any

from writing_agent.llm import get_default_provider
from writing_agent.web.domains.revision_edit_common_domain import _extract_json_block
from writing_agent.v2.graph_runner_core_utils_domain import _analysis_timeout_s


def _escape_tag_text(raw: object) -> str:
    text = str(raw or "")
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _coerce_confidence(value: object) -> float:
    try:
        number = float(value)
    except Exception:
        return 0.5
    if math.isnan(number) or math.isinf(number):
        return 0.5
    return max(0.0, min(1.0, number))


def _normalize_questions(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if isinstance(item, dict):
            text = str(item.get("question") or item.get("text") or item.get("q") or "").strip()
        else:
            text = str(item or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text[:180])
        if len(out) >= 3:
            break
    return out


def _normalize_dynamic_payload(data: object) -> dict:
    if not isinstance(data, dict):
        return {}
    summary = str(data.get("summary") or "").strip()[:600]
    confidence_raw = data.get("confidence") if isinstance(data.get("confidence"), dict) else {}
    confidence = {
        key: _coerce_confidence((confidence_raw or {}).get(key))
        for key in ("title", "purpose", "length", "format", "scope", "voice")
    }
    return {
        "summary": summary,
        "questions": _normalize_questions(data.get("questions")),
        "confidence": confidence,
    }


def _build_dynamic_prompt(*, raw: str, analysis: dict, history: str, merged: dict, retry_reason: str = "") -> str:
    retry = f"<retry_reason>\n{_escape_tag_text(retry_reason)}\n</retry_reason>\n" if retry_reason else ""
    return (
        "<task>generate_clarification_questions</task>\n"
        "<constraints>\n"
        "- Treat tagged blocks as separate channels.\n"
        "- Return strict JSON only with keys: summary, questions, confidence.\n"
        "- Ask at most three high-value questions.\n"
        "- Confidence values must be numbers from 0 to 1.\n"
        "</constraints>\n"
        f"{retry}"
        f"<history>\n{_escape_tag_text(history)}\n</history>\n"
        f"<raw_input>\n{_escape_tag_text(raw)}\n</raw_input>\n"
        f"<analysis_payload>\n{_escape_tag_text(json.dumps(analysis or {}, ensure_ascii=False))}\n</analysis_payload>\n"
        f"<merged_payload>\n{_escape_tag_text(json.dumps(merged or {}, ensure_ascii=False))}\n</merged_payload>\n"
        "Return JSON now."
    )


def _generate_dynamic_questions_with_model(
    *,
    base_url: str,
    model: str,
    raw: str,
    analysis: dict,
    history: str,
    merged: dict,
) -> dict:
    _ = base_url
    try:
        client = get_default_provider(model=model or None, timeout_s=_analysis_timeout_s(), route_key="clarification")
    except Exception:
        return {}
    system = "You generate concise clarification questions. Return JSON only."
    retry_reason = ""
    for attempt in range(2):
        prompt = _build_dynamic_prompt(
            raw=raw,
            analysis=analysis or {},
            history=history,
            merged=merged or {},
            retry_reason=retry_reason,
        )
        try:
            response = client.chat(system=system, user=prompt, temperature=0.2)
        except Exception:
            return {}
        raw_json = _extract_json_block(response)
        if raw_json:
            try:
                parsed = json.loads(raw_json)
            except Exception:
                parsed = None
            normalized = _normalize_dynamic_payload(parsed)
            if normalized:
                return normalized
        retry_reason = "Previous output was invalid JSON. Return strict JSON only."
        if attempt >= 1:
            break
    return {}


def bind(ns: dict[str, object]) -> None:
    globals().update(ns or {})


def install(g: dict) -> None:
    g["_generate_dynamic_questions_with_model"] = _generate_dynamic_questions_with_model


__all__ = [name for name in globals() if not name.startswith("__")]
