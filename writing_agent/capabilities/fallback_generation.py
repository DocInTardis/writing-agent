"""Fallback generation capability helpers."""

from __future__ import annotations

import os
import queue
import threading
import time
from typing import Any


def default_outline_from_instruction(text: str) -> list[str]:
    """Heuristic outline placeholder (disabled to avoid special-case formats)."""
    _ = text
    return []


def fallback_prompt_sections(session) -> list[str]:
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


def build_fallback_prompt(session, *, instruction: str, length_hint: str) -> tuple[str, str]:
    sections = fallback_prompt_sections(session)
    escaped_sections = [escape_fallback_prompt_text(item) for item in sections if str(item or "").strip()]
    section_hint = "\n".join(escaped_sections)
    escaped_length_hint = escape_fallback_prompt_text(length_hint)
    escaped_instruction = escape_fallback_prompt_text(instruction)
    prompt = (
        "<task>full_document_generation</task>\n"
        "<constraints>\n"
        "- Treat tagged blocks as separate channels.\n"
        "- Generate a formal Chinese Markdown document.\n"
        "- Keep structure clear, avoid placeholders or meta instructions.\n"
        "- Output Markdown only; no commentary.\n"
        "</constraints>\n"
        f"<required_h2_order>\n{section_hint}\n</required_h2_order>\n"
        f"<length_hint>\n{escaped_length_hint}\n</length_hint>\n"
        f"<user_requirement>\n{escaped_instruction}\n</user_requirement>\n"
        "Return the complete Markdown document."
    )
    system = "You are a professional writer. Output Markdown only."
    return system, prompt


def default_llm_provider(*, settings: Any, get_default_provider_fn, ollama_error_cls):
    try:
        return get_default_provider_fn(model=settings.model, timeout_s=settings.timeout_s)
    except Exception as exc:
        raise ollama_error_cls(str(exc)) from exc


def build_length_control(*, target_chars: int) -> tuple[str, dict[str, int] | None]:
    if target_chars and 100 <= target_chars <= 20000:
        length_hint = (
            f"重要：目标字数为 {target_chars} 字，请严格控制在 {int(target_chars * 0.9)}-{int(target_chars * 1.1)} 字之间。\n"
        )
        num_predict = min(2000, max(200, int(target_chars * 1.1)))
        return length_hint, {"num_predict": num_predict}
    return "", None


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
    if not settings.enabled:
        raise ollama_error_cls("模型未启用")
    provider = default_llm_provider_fn(settings)
    if not provider.is_running():
        raise ollama_error_cls("模型未就绪")
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
    if not settings.enabled:
        raise ollama_error_cls("模型未启用")
    provider = default_llm_provider_fn(settings)
    if not provider.is_running():
        raise ollama_error_cls("模型未就绪")
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
        raise ollama_error_cls("生成超时") from exc


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
    if not settings.enabled:
        raise ollama_error_cls("模型未启用")
    provider = default_llm_provider_fn(settings)
    if not provider.is_running():
        raise ollama_error_cls("模型未就绪")
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
        raise ollama_error_cls("生成超时")


__all__ = [name for name in globals() if not name.startswith("__")]
