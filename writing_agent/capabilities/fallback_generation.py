"""Fallback generation capability helpers."""

from __future__ import annotations

import json
import os
import queue
import re
import threading
import time
from typing import Any

_GENERIC_SESSION_TITLES = {
    "",
    "未命名文档",
    "untitled",
    "自动生成文档",
    "auto generated document",
}


def default_outline_from_instruction(text: str) -> list[str]:
    """Heuristic outline placeholder (disabled to avoid special-case formats)."""
    _ = text
    return []


def _extract_explicit_h2_order(instruction: str) -> list[str]:
    src = str(instruction or "").strip()
    if not src:
        return []
    patterns = [
        r"Use exactly these H2 section headings in this order:\s*(.+?)(?:\n|$)",
        r"Use these H2 headings in this order:\s*(.+?)(?:\n|$)",
        r"\u4f7f\u7528\u4ee5\u4e0b\u4e8c\u7ea7\u6807\u9898[:\uff1a]\s*(.+?)(?:\n|$)",
        r"\u5fc5\u987b\u6309\u987a\u5e8f\u8f93\u51fa\u4ee5\u4e0b\u4e8c\u7ea7\u6807\u9898[:\uff1a]\s*(.+?)(?:\n|$)",
    ]
    raw = ""
    for pattern in patterns:
        match = re.search(pattern, src, flags=re.IGNORECASE)
        if match:
            raw = str(match.group(1) or "").strip()
            break
    if not raw:
        return []
    parts = re.split(r"[;,\uff0c\u3001]+", raw)
    cleaned = [str(item or "").strip().strip(".\u3002\uff1a:; ") for item in parts if str(item or "").strip()]
    return [item for item in cleaned if item]


def fallback_prompt_sections(session, *, instruction: str = "") -> list[str]:
    explicit = _extract_explicit_h2_order(instruction)
    if explicit:
        return explicit
    if getattr(session, "template_outline", None):
        out: list[str] = []
        for item in (session.template_outline or []):
            try:
                _, title = item
            except Exception:
                continue
            title_text = str(title or "").strip()
            if title_text:
                out.append(title_text)
        return out
    if getattr(session, "template_required_h2", None):
        return [str(item or "").strip() for item in (session.template_required_h2 or []) if str(item or "").strip()]
    return []


def escape_fallback_prompt_text(raw: object) -> str:
    text = str(raw or "")
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _contains_non_ascii(text: object) -> bool:
    return any(ord(ch) > 127 for ch in str(text or ""))


def _unicode_escape_ascii(text: object) -> str:
    return json.dumps(str(text or ""), ensure_ascii=True)[1:-1]


def _derive_session_title(session) -> str:
    explicit = str(getattr(session, "title", "") or "").strip()
    if explicit and explicit.casefold() not in _GENERIC_SESSION_TITLES:
        return explicit
    request = getattr(session, "request", None)
    request_topic = str(getattr(request, "topic", "") or "").strip()
    if request_topic and request_topic.casefold() not in _GENERIC_SESSION_TITLES:
        return request_topic
    text = str(getattr(session, "doc_text", "") or "")
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            candidate = re.sub(r"^#+\s*", "", stripped).strip()
            if candidate and candidate.casefold() not in _GENERIC_SESSION_TITLES:
                return candidate
        if stripped:
            break
    return ""


def _clean_inline_value(raw: object) -> str:
    return str(raw or "").strip().strip(" .:;\"'")


def _extract_quoted_topic(instruction: str) -> str:
    src = str(instruction or "")
    patterns = [
        r"围绕[“\"]([^”\"\n]{4,120})[”\"]",
        r"关于[“\"]([^”\"\n]{4,120})[”\"]",
        r"以[“\"]([^”\"\n]{4,120})[”\"]为(?:题|主题)",
        r"[“\"]([^”\"\n]{6,120})[”\"]",
    ]
    for pattern in patterns:
        match = re.search(pattern, src, flags=re.IGNORECASE)
        if not match:
            continue
        value = _clean_inline_value(match.group(1))
        if value and value.casefold() not in _GENERIC_SESSION_TITLES:
            return value
    return ""


def _extract_exact_title(instruction: str, *, session) -> str:
    src = str(instruction or "")
    patterns = [
        r"Title must be exactly:\s*(.+?)(?:\n|$)",
        r"Title:\s*(.+?)(?:\n|$)",
        r"\u6807\u9898(?:\u5fc5\u987b)?(?:\u4e3a|\u662f|\u5199\u4e3a)?[:\uff1a]\s*(.+?)(?:\n|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, src, flags=re.IGNORECASE)
        if match:
            value = _clean_inline_value(match.group(1))
            if value:
                return value
    quoted_topic = _extract_quoted_topic(src)
    if quoted_topic:
        return quoted_topic
    return _derive_session_title(session)


def _extract_topic_focus(instruction: str, *, session, title: str) -> str:
    src = str(instruction or "")
    patterns = [
        r"Topic:\s*(.+?)(?:\n|$)",
        r"Research topic[:\uff1a]\s*(.+?)(?:\n|$)",
        r"\u4e3b\u9898[:\uff1a]\s*(.+?)(?:\n|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, src, flags=re.IGNORECASE)
        if match:
            value = _clean_inline_value(match.group(1))
            if value:
                return value
    quoted_topic = _extract_quoted_topic(src)
    if quoted_topic:
        return quoted_topic
    if title:
        return title
    return _derive_session_title(session)


def _required_h2_unicode_json(items: list[str]) -> str:
    escaped = [f'"{_unicode_escape_ascii(item)}"' for item in items if str(item or "").strip()]
    return "[" + ", ".join(escaped) + "]"


def _requires_ascii_safe_prompt(*, title: str, topic_focus: str, sections: list[str], instruction: str) -> bool:
    if _contains_non_ascii(title) or _contains_non_ascii(topic_focus) or _contains_non_ascii(instruction):
        return True
    return any(_contains_non_ascii(item) for item in (sections or []))


def _requires_reference_list(sections: list[str]) -> bool:
    tokens = {
        "\u53c2\u8003\u6587\u732e",
        "\u53c2\u8003\u8d44\u6599",
        "\u6587\u732e",
        "references",
        "bibliography",
    }
    for item in sections or []:
        normalized = str(item or "").strip().lower()
        if not normalized:
            continue
        if normalized in tokens:
            return True
    return False


def _has_section_keyword(sections: list[str], keywords: tuple[str, ...]) -> bool:
    normalized_sections = [str(item or "").strip().lower() for item in (sections or [])]
    for section in normalized_sections:
        for keyword in keywords:
            if keyword in section:
                return True
    return False


def _build_h3_guidance(sections: list[str]) -> str:
    lines: list[str] = []
    if _has_section_keyword(sections, ("研究方法", "方法", "method")):
        lines.append("- Under the methods section, include at least one H3 subsection such as a framework, design, or analytic path.")
    if _has_section_keyword(sections, ("结果", "分析", "discussion", "result")):
        lines.append("- Keep the results/analysis H2 itself populated with prose before any optional H3 subsections; do not make the H2 an empty shell.")
    return "\n".join(lines)


def build_fallback_prompt(session, *, instruction: str, length_hint: str) -> tuple[str, str]:
    sections = fallback_prompt_sections(session, instruction=instruction)
    exact_title = _extract_exact_title(instruction, session=session)
    topic_focus = _extract_topic_focus(instruction, session=session, title=exact_title)
    escaped_sections = [escape_fallback_prompt_text(item) for item in sections if str(item or "").strip()]
    section_hint = "\n".join(escaped_sections)
    escaped_length_hint = escape_fallback_prompt_text(length_hint)
    escaped_instruction = escape_fallback_prompt_text(instruction)
    escaped_title = escape_fallback_prompt_text(exact_title)
    escaped_topic = escape_fallback_prompt_text(topic_focus)
    needs_references = _requires_reference_list(sections)
    h3_guidance = _build_h3_guidance(sections)
    h3_rule = f"{h3_guidance}\n" if h3_guidance else ""

    if _requires_ascii_safe_prompt(
        title=exact_title,
        topic_focus=topic_focus,
        sections=sections,
        instruction=instruction,
    ):
        title_unicode = escape_fallback_prompt_text(_unicode_escape_ascii(exact_title))
        topic_unicode = escape_fallback_prompt_text(_unicode_escape_ascii(topic_focus))
        section_unicode_json = escape_fallback_prompt_text(_required_h2_unicode_json(sections))
        instruction_unicode = escape_fallback_prompt_text(_unicode_escape_ascii(instruction))
        reference_rule = (
            "- If the decoded H2 list contains a references section, provide 8 plausible Chinese academic references.\n"
            if needs_references
            else ""
        )
        prompt = (
            "<task>full_document_generation</task>\n"
            "<mode>ascii_safe_unicode_decoding</mode>\n"
            "<constraints>\n"
            "- Treat tagged blocks as separate channels.\n"
            "- Generate a formal Chinese Markdown document.\n"
            "- Decode Unicode escape sequences into Chinese and use the decoded Chinese strings exactly.\n"
            "- The first line must be a single H1 title built from the decoded title.\n"
            "- Output the required H2 headings exactly once, in the given order.\n"
            "- Do not add, delete, rename, or repeat H2 headings.\n"
            "- Keep the document tightly aligned with the decoded topic and requirement.\n"
            "- Keep structure clear and avoid placeholders, prompt echoes, or meta instructions.\n"
            f"{h3_rule}"
            "- Each paragraph should advance a concrete claim, mechanism, comparison, limitation, or evidence-grounded observation.\n"
            "- When making a strong factual, evaluative, comparative, or policy claim, support it with inline numeric citations such as [1] or [2][3].\n"
            "- In analysis and conclusion sections, do not leave standalone comparative or normative judgments without citations.\n"
            "- Avoid broad textbook-style introductions; anchor the discussion to concrete actors, service links, data flows, and governance mechanisms.\n"
            "- Avoid stock filler, repeated openings, generic transitions, and empty policy slogans.\n"
            f"{reference_rule}"
            "- Output Markdown only; no commentary.\n"
            "</constraints>\n"
            f"<title_unicode>\n{title_unicode}\n</title_unicode>\n"
            f"<topic_unicode>\n{topic_unicode}\n</topic_unicode>\n"
            f"<required_h2_unicode_json>\n{section_unicode_json}\n</required_h2_unicode_json>\n"
            f"<length_hint>\n{escaped_length_hint}\n</length_hint>\n"
            f"<user_requirement_unicode>\n{instruction_unicode}\n</user_requirement_unicode>\n"
            "Write the complete Chinese Markdown document now."
        )
    else:
        reference_rule = (
            "- If a references section is required, provide 8 plausible Chinese academic references.\n"
            if needs_references
            else ""
        )
        prompt = (
            "<task>full_document_generation</task>\n"
            "<constraints>\n"
            "- Treat tagged blocks as separate channels.\n"
            "- Generate a formal Chinese Markdown document.\n"
            "- The first line must be a single H1 title.\n"
            "- Use exactly the required H2 headings in the given order.\n"
            "- Do not add, delete, rename, or repeat H2 headings.\n"
            "- Keep structure clear and avoid placeholders, prompt echoes, or meta instructions.\n"
            f"{h3_rule}"
            "- Each paragraph should advance a concrete claim, mechanism, comparison, limitation, or evidence-grounded observation.\n"
            "- When making a strong factual, evaluative, comparative, or policy claim, support it with inline numeric citations such as [1] or [2][3].\n"
            "- In analysis and conclusion sections, do not leave standalone comparative or normative judgments without citations.\n"
            "- Avoid broad textbook-style introductions; anchor the discussion to concrete actors, service links, data flows, and governance mechanisms.\n"
            "- Avoid stock filler, repeated openings, generic transitions, and empty policy slogans.\n"
            f"{reference_rule}"
            "- Output Markdown only; no commentary.\n"
            "</constraints>\n"
            f"<exact_title>\n{escaped_title}\n</exact_title>\n"
            f"<topic_focus>\n{escaped_topic}\n</topic_focus>\n"
            f"<required_h2_order>\n{section_hint}\n</required_h2_order>\n"
            f"<length_hint>\n{escaped_length_hint}\n</length_hint>\n"
            f"<user_requirement>\n{escaped_instruction}\n</user_requirement>\n"
            "Return the complete Markdown document."
        )
    system = "You are a professional writer. Output Markdown only."
    return system, prompt


def default_llm_provider(*, settings: Any, get_default_provider_fn, ollama_error_cls):
    try:
        provider_name = str(os.environ.get("WRITING_AGENT_LLM_PROVIDER", "openai") or "openai").strip().lower()
        model = settings.model if provider_name == "ollama" else None
        return get_default_provider_fn(model=model, timeout_s=settings.timeout_s)
    except Exception as exc:
        raise ollama_error_cls(str(exc)) from exc


def build_length_control(*, target_chars: int) -> tuple[str, dict[str, int] | None]:
    if target_chars and 100 <= target_chars <= 20000:
        lo = int(target_chars * 0.9)
        hi = int(target_chars * 1.1)
        length_hint = (
            f"CRITICAL: the output MUST be between {lo} and {hi} Chinese characters. "
            f"Do not exceed {hi} characters. Do not write fewer than {lo} characters. "
            f"Count every Chinese character, punctuation, and digit toward the total.\n"
        )
        num_predict = min(4000, max(200, int(target_chars * 1.1)))
        return length_hint, {"num_predict": num_predict}
    return "", None


def _ensure_provider_ready(*, settings: Any, provider, ollama_error_cls) -> None:
    if not bool(getattr(settings, "enabled", False)):
        raise ollama_error_cls("model provider disabled")
    if hasattr(provider, "is_running") and callable(provider.is_running) and not provider.is_running():
        raise ollama_error_cls("model provider not ready")


def single_pass_generate(
    *,
    session,
    instruction: str,
    current_text: str,
    target_chars: int = 0,
    get_ollama_settings_fn,
    default_llm_provider_fn,
    sanitize_output_text_fn,
    ollama_error_cls,
) -> str:
    _ = current_text
    settings = get_ollama_settings_fn()
    provider = default_llm_provider_fn(settings)
    _ensure_provider_ready(settings=settings, provider=provider, ollama_error_cls=ollama_error_cls)
    length_hint, options = build_length_control(target_chars=target_chars)
    system, prompt = build_fallback_prompt(session, instruction=instruction, length_hint=length_hint)
    raw = provider.chat(system=system, user=prompt, temperature=0.5, options=options)
    return sanitize_output_text_fn(raw)


def single_pass_generate_with_heartbeat(
    *,
    session,
    instruction: str,
    current_text: str,
    target_chars: int = 0,
    heartbeat_callback=None,
    get_ollama_settings_fn,
    default_llm_provider_fn,
    sanitize_output_text_fn,
    ollama_error_cls,
):
    _ = current_text
    settings = get_ollama_settings_fn()
    provider = default_llm_provider_fn(settings)
    _ensure_provider_ready(settings=settings, provider=provider, ollama_error_cls=ollama_error_cls)
    length_hint, options = build_length_control(target_chars=target_chars)
    system, prompt = build_fallback_prompt(session, instruction=instruction, length_hint=length_hint)
    result_queue: queue.Queue = queue.Queue()

    def _generate_worker():
        try:
            raw = provider.chat(system=system, user=prompt, temperature=0.5, options=options)
            result_queue.put(("ok", sanitize_output_text_fn(raw)))
        except Exception as exc:
            result_queue.put(("error", exc))

    thread = threading.Thread(target=_generate_worker, daemon=True)
    thread.start()
    heartbeat_interval = 5.0
    last_heartbeat = time.time()
    while thread.is_alive():
        try:
            kind, payload = result_queue.get(timeout=0.5)
            if kind == "ok":
                return payload
            raise payload
        except queue.Empty:
            now = time.time()
            if heartbeat_callback and (now - last_heartbeat) >= heartbeat_interval:
                heartbeat_callback()
                last_heartbeat = now
    try:
        kind, payload = result_queue.get(timeout=1.0)
        if kind == "ok":
            return payload
        raise payload
    except queue.Empty as exc:
        raise ollama_error_cls("generation timeout") from exc


def single_pass_generate_stream(
    *,
    session,
    instruction: str,
    current_text: str,
    target_chars: int = 0,
    default_llm_provider_fn,
    get_ollama_settings_fn,
    sanitize_output_text_fn,
    ollama_error_cls,
):
    _ = current_text
    settings = get_ollama_settings_fn()
    provider = default_llm_provider_fn(settings)
    _ensure_provider_ready(settings=settings, provider=provider, ollama_error_cls=ollama_error_cls)
    length_hint, options = build_length_control(target_chars=target_chars)
    system, prompt = build_fallback_prompt(session, instruction=instruction, length_hint=length_hint)
    buf = ""
    emit_buf = ""
    last_emit = time.time()
    chunk_min = int(os.environ.get("WRITING_AGENT_STREAM_CHUNK", "60"))
    chunk_min = max(20, min(400, chunk_min))
    for delta in provider.chat_stream(system=system, user=prompt, temperature=0.5, options=options):
        buf += delta
        emit_buf += delta
        now = time.time()
        if len(emit_buf) >= chunk_min or (now - last_emit) > 1.2:
            yield {"event": "section", "phase": "delta", "section": "", "delta": emit_buf}
            emit_buf = ""
            last_emit = now
    if emit_buf:
        yield {"event": "section", "phase": "delta", "section": "", "delta": emit_buf}
    if buf.strip():
        yield {"event": "result", "text": sanitize_output_text_fn(buf)}
    else:
        raise ollama_error_cls("generation timeout")


__all__ = [name for name in globals() if not name.startswith("__")]
