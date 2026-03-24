"""Provider settings and runtime provider helpers for split runtime orchestration."""

# Prompt-contract markers retained for provider preflight chat guards:
# <task>runtime_provider_preflight</task>
# <constraints>

from __future__ import annotations

import os
import queue
import threading
from dataclasses import dataclass

from writing_agent.llm.factory import get_default_provider as _factory_default_provider
from writing_agent.llm.settings import get_ollama_settings
from writing_agent.v2.global_config import FAILURE_API_PROVIDER_UNREACHABLE, classify_provider_error


def _base():
    from writing_agent.v2 import graph_runner_runtime_common_domain as base

    return base


@dataclass(frozen=True)
class RuntimeProviderSettings:
    enabled: bool
    base_url: str
    model: str
    timeout_s: float


_GENERATION_SLOT_MAP: dict[tuple[str, str, int], threading.BoundedSemaphore] = {}


def resolve_provider_settings(*, runtime_api, provider_name: str, provider_snapshot: dict | None = None) -> tuple[RuntimeProviderSettings, set[str]]:
    _ = provider_snapshot
    normalized = str(provider_name or "").strip().lower()
    if normalized == "ollama":
        settings = runtime_api.get_ollama_settings() if hasattr(runtime_api, 'get_ollama_settings') else get_ollama_settings()
        installed = set(runtime_api._ollama_installed_models()) if hasattr(runtime_api, '_ollama_installed_models') else set()
        return RuntimeProviderSettings(
            enabled=bool(settings.enabled),
            base_url=str(settings.base_url or "").strip(),
            model=str(settings.model or "").strip(),
            timeout_s=float(settings.timeout_s),
        ), installed
    base_url = str(os.environ.get('WRITING_AGENT_OPENAI_BASE_URL', 'https://api.openai.com/v1')).strip()
    model = str(os.environ.get('WRITING_AGENT_OPENAI_MODEL', 'gpt-4o-mini')).strip() or 'gpt-4o-mini'
    timeout_raw = str(os.environ.get('WRITING_AGENT_OPENAI_TIMEOUT_S', os.environ.get('WRITING_AGENT_PROVIDER_TIMEOUT_S', '60'))).strip() or '60'
    try:
        timeout_s = max(10.0, float(timeout_raw))
    except Exception:
        timeout_s = 60.0
    enabled = bool(base_url)
    return RuntimeProviderSettings(enabled=enabled, base_url=base_url, model=model, timeout_s=timeout_s), set()


def select_preflight_model(*, config, settings: RuntimeProviderSettings) -> str:
    return str(getattr(config, 'aggregator_model', None) or os.environ.get('WRITING_AGENT_AGG_MODEL', '') or settings.model).strip() or settings.model


def create_preflight_provider(*, runtime_api, provider_name: str, settings: RuntimeProviderSettings, preflight_model: str, run_id: str):
    provider_factory = getattr(runtime_api, 'get_default_provider', None)
    if str(provider_name or "").strip().lower() == "ollama":
        if callable(provider_factory) and provider_factory is not _factory_default_provider:
            return provider_factory(model=preflight_model, timeout_s=float(settings.timeout_s), route_key=f'v2.runtime.preflight.{run_id}')
        return runtime_api.OllamaClient(base_url=settings.base_url, model=preflight_model, timeout_s=float(settings.timeout_s))
    return runtime_api.get_default_provider(model=preflight_model, timeout_s=float(settings.timeout_s), route_key=f'v2.runtime.preflight.{run_id}')


def resolve_runtime_models(*, runtime_api, provider_name: str, settings: RuntimeProviderSettings, installed: set[str], config) -> tuple[str, list[str], str, str]:
    agg_model = str(getattr(config, 'aggregator_model', None) or os.environ.get('WRITING_AGENT_AGG_MODEL', '') or settings.model).strip() or settings.model
    if provider_name == 'ollama':
        worker_models = list(getattr(config, 'worker_models', None) or runtime_api._default_worker_models(preferred=settings.model))
        if hasattr(runtime_api, '_select_models_by_memory'):
            worker_models = list(runtime_api._select_models_by_memory(worker_models, fallback=settings.model))
        if installed:
            worker_models = [model for model in worker_models if model in installed] or [settings.model]
    else:
        worker_models = [str(model).strip() for model in (getattr(config, 'worker_models', None) or [settings.model]) if str(model).strip()]
        if not worker_models:
            worker_models = [settings.model]
    main_model, support_model = runtime_api._pick_draft_models(worker_models, agg_model=agg_model, fallback=settings.model)
    main_model = str(main_model or settings.model).strip() or settings.model
    support_model = str(support_model or '').strip()
    return agg_model, worker_models, main_model, support_model


def _provider_default_model(provider_name: str) -> str:
    return str(os.environ.get(f"WRITING_AGENT_{str(provider_name or '').upper()}_MODEL", "")).strip() or str(os.environ.get("WRITING_AGENT_OPENAI_MODEL", "gpt-4.1-mini")).strip()


def _provider_timeout_s(provider_name: str) -> float:
    raw = str(os.environ.get(f"WRITING_AGENT_{str(provider_name or '').upper()}_TIMEOUT_S", "")).strip() or str(os.environ.get("WRITING_AGENT_PROVIDER_TIMEOUT_S", "60")).strip()
    try:
        return max(10.0, float(raw))
    except Exception:
        return 60.0


def _provider_default_per_model_concurrency(provider_name: str) -> int:
    normalized = str(provider_name or "").strip().lower()
    raw = (
        str(os.environ.get("WRITING_AGENT_PER_MODEL_CONCURRENCY", "")).strip()
        or str(os.environ.get(f"WRITING_AGENT_{normalized.upper()}_PER_MODEL_CONCURRENCY", "")).strip()
        or str(os.environ.get("WRITING_AGENT_PROVIDER_PER_MODEL_CONCURRENCY", "")).strip()
    )
    if raw:
        try:
            return max(1, min(16, int(raw)))
        except Exception:
            pass
    if normalized == "openai":
        return 4
    if normalized == "ollama":
        return 1
    return 2


def _generation_slot_enabled() -> bool:
    return _base()._env_flag("WRITING_AGENT_GENERATION_SLOT_ENABLED", "0")


def _generation_slot_limit(provider_name: str, model: str) -> int:
    _ = model
    raw = str(os.environ.get("WRITING_AGENT_GENERATION_SLOT_LIMIT", "")).strip()
    if raw:
        try:
            return max(1, int(raw))
        except Exception:
            pass
    return _provider_default_per_model_concurrency(provider_name)


def _generation_slot(provider_name: str, model: str):
    limit = _generation_slot_limit(provider_name, model)
    key = (str(provider_name or "").strip().lower(), str(model or "").strip(), limit)
    slot = _GENERATION_SLOT_MAP.get(key)
    if slot is None:
        slot = threading.BoundedSemaphore(limit)
        _GENERATION_SLOT_MAP[key] = slot
    return slot


def _call_with_generation_slot(*, provider_name: str, model: str, fn, out_queue: queue.Queue[dict] | None = None, section: str = "", section_id: str = "", stage: str = "section"):
    _ = out_queue, section, section_id, stage
    if not _generation_slot_enabled():
        return fn()
    slot = _generation_slot(provider_name, model)
    acquired = False
    try:
        slot.acquire()
        acquired = True
        return fn()
    finally:
        if acquired:
            slot.release()


def _guarded_stream_structured_blocks(*, provider_name: str, model: str, out_queue: queue.Queue[dict], section: str, section_id: str, **kwargs):
    return _call_with_generation_slot(
        provider_name=provider_name,
        model=model,
        fn=lambda: _base()._stream_structured_blocks(out_queue=out_queue, section=section, section_id=section_id, **kwargs),
        out_queue=out_queue,
        section=section,
        section_id=section_id,
        stage="stream",
    )


def _provider_default_evidence_workers(provider_name: str, *, sections_count: int) -> int:
    cap = max(1, int(sections_count or 0))
    raw = (
        str(os.environ.get("WRITING_AGENT_EVIDENCE_WORKERS", "")).strip()
        or str(os.environ.get(f"WRITING_AGENT_{str(provider_name or '').upper()}_EVIDENCE_WORKERS", "")).strip()
    )
    if raw:
        try:
            return max(1, min(cap, int(raw)))
        except Exception:
            pass
    base = _provider_default_per_model_concurrency(provider_name)
    return max(1, min(cap, base + 2))


def _provider_preflight(*, provider, model: str, provider_name: str) -> tuple[bool, str]:
    _ = model
    normalized = str(provider_name or "").strip().lower()
    chat_enabled = _base()._env_flag("WRITING_AGENT_PROVIDER_PREFLIGHT_CHAT", "1")
    try:
        if normalized == "ollama" and hasattr(provider, "is_running") and callable(provider.is_running) and not provider.is_running():
            return False, FAILURE_API_PROVIDER_UNREACHABLE
        if chat_enabled and hasattr(provider, "chat") and callable(provider.chat):
            provider.chat(system="Return OK.", user="ping", temperature=0.0, options={"max_tokens": 4})
        return True, ""
    except Exception as exc:
        return False, classify_provider_error(str(exc))


__all__ = [name for name in globals() if not name.startswith("__")]
