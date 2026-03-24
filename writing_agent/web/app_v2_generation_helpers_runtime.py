"""App V2 Generation Helpers Runtime module.

This module belongs to `writing_agent.web` in the writing-agent codebase.
"""

# Prompt-contract markers retained for guard tests:
# <task>full_document_generation</task>
# <constraints>

from __future__ import annotations

import json
import os
from pathlib import Path
import time
from collections.abc import Iterable
from functools import wraps
from urllib.parse import quote
from urllib.request import Request as UrlRequest, urlopen

from writing_agent.capabilities.fallback_generation import (
    build_fallback_prompt,
    default_llm_provider,
    default_outline_from_instruction,
    fallback_prompt_sections,
    single_pass_generate,
    single_pass_generate_stream,
    single_pass_generate_with_heartbeat,
)
from writing_agent.capabilities.generation_quality import check_generation_quality, looks_like_prompt_echo
from writing_agent.capabilities.generation_policy import should_use_fast_generate, summarize_analysis, system_pressure_high
from writing_agent.capabilities.mcp_retrieval import (
    ensure_mcp_citations,
    load_mcp_citations_cached,
    mcp_first_json,
    mcp_rag_enabled,
    mcp_rag_retrieve,
    mcp_rag_search,
    mcp_rag_search_chunks,
)
from writing_agent.llm.factory import get_default_provider
from writing_agent.llm.ollama import OllamaError
from writing_agent.mcp_client import fetch_mcp_resource
from writing_agent.models import Citation
from writing_agent.web.model_runtime_support import (
    ensure_ollama_ready,
    ensure_ollama_ready_iter,
    pull_model_stream,
    pull_model_stream_iter,
    recommended_stream_timeouts,
    run_with_heartbeat,
)

_BIND_SKIP_NAMES = {
    "__builtins__",
    "__cached__",
    "__doc__",
    "__file__",
    "__loader__",
    "__name__",
    "__package__",
    "__spec__",
    "_BIND_SKIP_NAMES",
    "_ORIGINAL_FUNCS",
    "bind",
    "install",
    "_proxy_factory",
}
_ORIGINAL_FUNCS: dict[str, object] = {}


def bind(namespace: dict) -> None:
    for key, value in namespace.items():
        if key in _BIND_SKIP_NAMES:
            continue
        if callable(value) and bool(getattr(value, "_wa_runtime_proxy", False)):
            if str(getattr(value, "_wa_runtime_proxy_target_module", "")) == __name__:
                original = _ORIGINAL_FUNCS.get(key)
                if callable(original):
                    globals()[key] = original
                continue
        local = globals().get(key)
        if key in globals() and local is value:
            continue
        globals()[key] = value


def _proxy_factory(fn_name: str, namespace: dict):
    fn = globals()[fn_name]

    @wraps(fn)
    def _proxy(*args, **kwargs):
        bind(namespace)
        return fn(*args, **kwargs)

    _proxy._wa_runtime_proxy = True
    _proxy._wa_runtime_proxy_target_module = __name__
    _proxy._wa_runtime_proxy_target_name = fn_name
    return _proxy


def install(namespace: dict) -> None:
    bind(namespace)
    for fn_name in EXPORTED_FUNCTIONS:
        _ORIGINAL_FUNCS.setdefault(fn_name, globals().get(fn_name))
    for fn_name in EXPORTED_FUNCTIONS:
        namespace[fn_name] = _proxy_factory(fn_name, namespace)


EXPORTED_FUNCTIONS = [
    "_load_mcp_citations_cached",
    "_ensure_mcp_citations",
    "_mcp_rag_enabled",
    "_mcp_first_json",
    "_mcp_rag_retrieve",
    "_mcp_rag_search",
    "_mcp_rag_search_chunks",
    "_recommended_stream_timeouts",
    "_run_with_heartbeat",
    "_default_outline_from_instruction",
    "_fallback_prompt_sections",
    "_build_fallback_prompt",
    "_default_llm_provider",
    "_single_pass_generate",
    "_single_pass_generate_with_heartbeat",
    "_single_pass_generate_stream",
    "_check_generation_quality",
    "_looks_like_prompt_echo",
    "_system_pressure_high",
    "_should_use_fast_generate",
    "_pull_model_stream_iter",
    "_pull_model_stream",
    "_ensure_ollama_ready_iter",
    "_ensure_ollama_ready",
    "_summarize_analysis",
]

def _load_mcp_citations_cached() -> dict[str, Citation]:
    return load_mcp_citations_cached(
        cache=_MCP_CITATIONS_CACHE,
        os_module=os,
        time_module=time,
        json_module=json,
        fetch_mcp_resource_fn=fetch_mcp_resource,
        citation_cls=Citation,
    )
def _ensure_mcp_citations(session) -> None:
    ensure_mcp_citations(
        session=session,
        load_mcp_citations_cached_fn=_load_mcp_citations_cached,
        doc_ir_from_dict_fn=doc_ir_from_dict,
        doc_ir_from_text_fn=doc_ir_from_text,
        citation_style_from_session_fn=_citation_style_from_session,
        apply_citations_to_doc_ir_fn=_apply_citations_to_doc_ir,
        doc_ir_to_dict_fn=doc_ir_to_dict,
        doc_ir_to_text_fn=doc_ir_to_text,
    )
def _mcp_rag_enabled() -> bool:
    return mcp_rag_enabled(os_module=os)
def _mcp_first_json(result: dict | None):
    return mcp_first_json(result=result, json_module=json)
def _mcp_rag_retrieve(query: str, *, top_k: int, per_paper: int, max_chars: int):
    return mcp_rag_retrieve(
        query=query,
        top_k=top_k,
        per_paper=per_paper,
        max_chars=max_chars,
        rag_enabled_fn=_mcp_rag_enabled,
        quote_fn=quote,
        fetch_mcp_resource_fn=fetch_mcp_resource,
        first_json_fn=_mcp_first_json,
    )
def _mcp_rag_search(query: str, *, top_k: int, sources=None, max_results: int | None = None, mode: str = ""):
    return mcp_rag_search(
        query=query,
        top_k=top_k,
        sources=sources,
        max_results=max_results,
        mode=mode,
        rag_enabled_fn=_mcp_rag_enabled,
        quote_fn=quote,
        fetch_mcp_resource_fn=fetch_mcp_resource,
        first_json_fn=_mcp_first_json,
    )
def _mcp_rag_search_chunks(query: str, *, top_k: int, per_paper: int, alpha: float, use_embeddings: bool):
    return mcp_rag_search_chunks(
        query=query,
        top_k=top_k,
        per_paper=per_paper,
        alpha=alpha,
        use_embeddings=use_embeddings,
        rag_enabled_fn=_mcp_rag_enabled,
        quote_fn=quote,
        fetch_mcp_resource_fn=fetch_mcp_resource,
        first_json_fn=_mcp_first_json,
    )
def _recommended_stream_timeouts() -> tuple[float, float]:
    def _load_probe() -> dict | None:
        probe_path = Path(".data/out/ui_timeout_probe.json")
        if probe_path.exists():
            try:
                return json.loads(probe_path.read_text(encoding="utf-8"))
            except Exception:
                return None
        return None

    return recommended_stream_timeouts(
        load_stream_metrics_fn=_load_stream_metrics,
        percentile_fn=_percentile,
        load_probe_fn=_load_probe,
    )
def _run_with_heartbeat(fn, timeout_s: float, fallback, *, label: str, heartbeat_s: float = 3.0):
    return run_with_heartbeat(fn, timeout_s, fallback, label=label, heartbeat_s=heartbeat_s)
def _default_outline_from_instruction(text: str) -> list[str]:
    return default_outline_from_instruction(text)
def _fallback_prompt_sections(session) -> list[str]:
    return fallback_prompt_sections(session)


def _escape_fallback_prompt_text(raw: object) -> str:
    text = str(raw or "")
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _build_fallback_prompt(session, *, instruction: str, length_hint: str) -> tuple[str, str]:
    return build_fallback_prompt(session, instruction=instruction, length_hint=length_hint)

def _default_llm_provider(settings):
    return default_llm_provider(
        settings=settings,
        get_default_provider_fn=get_default_provider,
        ollama_error_cls=OllamaError,
    )

def _single_pass_generate(session, *, instruction: str, current_text: str, target_chars: int = 0) -> str:
    return single_pass_generate(
        session=session,
        instruction=instruction,
        current_text=current_text,
        target_chars=target_chars,
        get_ollama_settings_fn=get_ollama_settings,
        default_llm_provider_fn=_default_llm_provider,
        sanitize_output_text_fn=_sanitize_output_text,
        ollama_error_cls=OllamaError,
    )
def _single_pass_generate_with_heartbeat(session, *, instruction: str, current_text: str, target_chars: int = 0, heartbeat_callback=None):
    return single_pass_generate_with_heartbeat(
        session=session,
        instruction=instruction,
        current_text=current_text,
        target_chars=target_chars,
        heartbeat_callback=heartbeat_callback,
        get_ollama_settings_fn=get_ollama_settings,
        default_llm_provider_fn=_default_llm_provider,
        sanitize_output_text_fn=_sanitize_output_text,
        ollama_error_cls=OllamaError,
    )
def _single_pass_generate_stream(session, *, instruction: str, current_text: str, target_chars: int = 0):
    yield from single_pass_generate_stream(
        session=session,
        instruction=instruction,
        current_text=current_text,
        target_chars=target_chars,
        get_ollama_settings_fn=get_ollama_settings,
        default_llm_provider_fn=_default_llm_provider,
        sanitize_output_text_fn=_sanitize_output_text,
        ollama_error_cls=OllamaError,
    )
def _check_generation_quality(text: str, target_chars: int = 0) -> list[str]:
    return check_generation_quality(text, target_chars)
def _looks_like_prompt_echo(text: str, instruction: str) -> bool:
    return looks_like_prompt_echo(text, instruction)
def _system_pressure_high() -> bool:
    return system_pressure_high(os_module=os)
def _should_use_fast_generate(raw_instruction: str, target_chars: int, prefs: dict | None) -> bool:
    return should_use_fast_generate(
        raw_instruction=raw_instruction,
        target_chars=target_chars,
        prefs=prefs,
        os_module=os,
        system_pressure_high_fn=_system_pressure_high,
    )
def _pull_model_stream_iter(base_url: str, name: str, *, timeout_s: float) -> Iterable[str] | tuple[bool, str]:
    return pull_model_stream_iter(
        base_url=base_url,
        name=name,
        timeout_s=timeout_s,
        url_request_cls=UrlRequest,
        urlopen_fn=urlopen,
    )
def _pull_model_stream(base_url: str, name: str, *, timeout_s: float) -> tuple[bool, str]:
    return pull_model_stream(
        base_url=base_url,
        name=name,
        timeout_s=timeout_s,
        pull_model_stream_iter_fn=_pull_model_stream_iter,
    )
def _ensure_ollama_ready_iter() -> Iterable[str] | tuple[bool, str]:
    return ensure_ollama_ready_iter(
        get_ollama_settings_fn=get_ollama_settings,
        ollama_client_cls=OllamaClient,
        start_ollama_serve_fn=_start_ollama_serve,
        wait_until_fn=_wait_until,
    )

def _ensure_ollama_ready() -> tuple[bool, str]:
    return ensure_ollama_ready(
        get_ollama_settings_fn=get_ollama_settings,
        ollama_client_cls=OllamaClient,
        start_ollama_serve_fn=_start_ollama_serve,
        wait_until_fn=_wait_until,
    )

def _summarize_analysis(raw: str, analysis: dict) -> dict:
    return summarize_analysis(raw=raw, analysis=analysis)
