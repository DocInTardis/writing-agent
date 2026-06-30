"""Failover provider helpers for GPT-first generation."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from writing_agent.llm.provider import LLMProvider, LLMProviderError

_QUOTA_TOKENS = (
    "api_insufficient_quota",
    "insufficient_quota",
    "quota exceeded",
    "quota_exceeded",
    "exceeded your current quota",
    "billing_hard_limit",
    "billing hard limit",
    "hard limit reached",
    "credit balance is too low",
    "余额不足",
    "额度不足",
    "配额不足",
)

_RETRYABLE_TOKENS = _QUOTA_TOKENS + (
    "api_auth_failed",
    "unauthorized",
    "invalid api key",
    "incorrect api key",
    "api_provider_unreachable",
    "api_provider_request_failed",
    "connection aborted",
    "connection reset",
    "timed out",
    "timeout",
    "temporary failure",
    "name or service not known",
    "remote end closed connection",
)


def looks_like_quota_error(message: str) -> bool:
    text = str(message or "").strip().lower()
    if not text:
        return False
    return any(token in text for token in _QUOTA_TOKENS)


def looks_like_retryable_openai_error(message: str) -> bool:
    text = str(message or "").strip().lower()
    if not text:
        return False
    return any(token in text for token in _RETRYABLE_TOKENS)


@dataclass(frozen=True)
class OpenAIKeyPoolProvider(LLMProvider):
    """Try a pool of OpenAI-compatible providers before giving up."""

    providers: tuple[LLMProvider, ...]
    provider_labels: tuple[str, ...] = ()

    def __getattr__(self, name: str) -> Any:
        if not self.providers:
            raise AttributeError(name)
        return getattr(self.providers[0], name)

    def _label_for(self, index: int) -> str:
        if index < len(self.provider_labels):
            label = str(self.provider_labels[index] or "").strip()
            if label:
                return label
        return f"candidate_{index + 1}"

    def is_running(self) -> bool:
        for provider in self.providers:
            try:
                if provider.is_running():
                    return True
            except Exception:
                continue
        return False

    def chat(self, *, system: str, user: str, temperature: float = 0.2, options: dict[str, Any] | None = None) -> str:
        last_exc: Exception | None = None
        failures: list[str] = []
        for idx, provider in enumerate(self.providers):
            try:
                return provider.chat(system=system, user=user, temperature=temperature, options=options)
            except Exception as exc:
                last_exc = exc
                message = str(exc or "")
                failures.append(f"{self._label_for(idx)}={message}")
                if idx + 1 < len(self.providers) and looks_like_retryable_openai_error(message):
                    continue
                break
        if last_exc is None:
            raise LLMProviderError("openai_key_pool_failed:chat:no_candidates")
        if len(failures) > 1:
            raise LLMProviderError(f"openai_key_pool_failed:chat: {'; '.join(failures)}") from last_exc
        raise LLMProviderError(str(last_exc)) from last_exc

    def chat_stream(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.2,
        options: dict[str, Any] | None = None,
    ) -> Iterable[str]:
        last_exc: Exception | None = None
        failures: list[str] = []
        for idx, provider in enumerate(self.providers):
            emitted = False
            try:
                for chunk in provider.chat_stream(system=system, user=user, temperature=temperature, options=options):
                    emitted = True
                    yield chunk
                return
            except Exception as exc:
                last_exc = exc
                message = str(exc or "")
                failures.append(f"{self._label_for(idx)}={message}")
                if emitted:
                    raise LLMProviderError(message) from exc
                if idx + 1 < len(self.providers) and looks_like_retryable_openai_error(message):
                    continue
                break
        if last_exc is None:
            raise LLMProviderError("openai_key_pool_failed:chat_stream:no_candidates")
        if len(failures) > 1:
            raise LLMProviderError(f"openai_key_pool_failed:chat_stream: {'; '.join(failures)}") from last_exc
        raise LLMProviderError(str(last_exc)) from last_exc

    def embeddings(self, *, prompt: str, model: str | None = None) -> list[float]:
        last_exc: Exception | None = None
        failures: list[str] = []
        for idx, provider in enumerate(self.providers):
            try:
                return provider.embeddings(prompt=prompt, model=model)
            except Exception as exc:
                last_exc = exc
                message = str(exc or "")
                failures.append(f"{self._label_for(idx)}={message}")
                if idx + 1 < len(self.providers) and looks_like_retryable_openai_error(message):
                    continue
                break
        if last_exc is None:
            raise LLMProviderError("openai_key_pool_failed:embeddings:no_candidates")
        if len(failures) > 1:
            raise LLMProviderError(f"openai_key_pool_failed:embeddings: {'; '.join(failures)}") from last_exc
        raise LLMProviderError(str(last_exc)) from last_exc


@dataclass(frozen=True)
class OpenAIQuotaFallbackProvider(LLMProvider):
    """Use OpenAI first and fall back to Ollama only on quota/billing errors.

    Embeddings stay on the primary provider because local generation models may not
    support the embedding route configured for the OpenAI path.
    """

    primary_provider: LLMProvider
    fallback_provider: LLMProvider
    primary_name: str = "openai"
    fallback_name: str = "ollama"

    def __getattr__(self, name: str) -> Any:
        return getattr(self.primary_provider, name)

    def is_running(self) -> bool:
        return bool(self.primary_provider.is_running())

    def _raise_or_fallback(self, *, operation: str, reason: Exception, fallback_fn):
        message = str(reason or "")
        if not looks_like_quota_error(message):
            raise LLMProviderError(message) from reason
        try:
            return fallback_fn()
        except Exception as fallback_exc:
            raise LLMProviderError(
                f"{self.primary_name}_quota_fallback_failed:{operation}: "
                f"primary={message}; fallback={fallback_exc}"
            ) from fallback_exc

    def chat(self, *, system: str, user: str, temperature: float = 0.2, options: dict[str, Any] | None = None) -> str:
        try:
            return self.primary_provider.chat(system=system, user=user, temperature=temperature, options=options)
        except Exception as exc:
            return self._raise_or_fallback(
                operation="chat",
                reason=exc,
                fallback_fn=lambda: self.fallback_provider.chat(
                    system=system,
                    user=user,
                    temperature=temperature,
                    options=options,
                ),
            )

    def chat_stream(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.2,
        options: dict[str, Any] | None = None,
    ) -> Iterable[str]:
        emitted = False
        try:
            for chunk in self.primary_provider.chat_stream(
                system=system,
                user=user,
                temperature=temperature,
                options=options,
            ):
                emitted = True
                yield chunk
            return
        except Exception as exc:
            if emitted or not looks_like_quota_error(str(exc or "")):
                raise LLMProviderError(str(exc)) from exc
            try:
                for chunk in self.fallback_provider.chat_stream(
                    system=system,
                    user=user,
                    temperature=temperature,
                    options=options,
                ):
                    yield chunk
            except Exception as fallback_exc:
                raise LLMProviderError(
                    f"{self.primary_name}_quota_fallback_failed:chat_stream: "
                    f"primary={exc}; fallback={fallback_exc}"
                ) from fallback_exc

    def embeddings(self, *, prompt: str, model: str | None = None) -> list[float]:
        try:
            return self.primary_provider.embeddings(prompt=prompt, model=model)
        except Exception as exc:
            raise LLMProviderError(str(exc)) from exc
