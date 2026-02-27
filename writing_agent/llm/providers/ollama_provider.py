"""Ollama Provider module.

This module belongs to `writing_agent.llm.providers` in the writing-agent codebase.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from writing_agent.llm.ollama import OllamaClient
from writing_agent.llm.provider import LLMProvider
from writing_agent.llm.settings import OllamaSettings


@dataclass(frozen=True)
class OllamaProvider(LLMProvider):
    client: OllamaClient

    @classmethod
    def from_settings(
        cls,
        settings: OllamaSettings,
        *,
        model: str | None = None,
        timeout_s: float | None = None,
    ) -> "OllamaProvider":
        chosen_model = str(model or settings.model or "").strip() or settings.model
        chosen_timeout = float(timeout_s if timeout_s is not None else settings.timeout_s)
        return cls(
            client=OllamaClient(
                base_url=settings.base_url,
                model=chosen_model,
                timeout_s=chosen_timeout,
            )
        )

    def is_running(self) -> bool:
        return self.client.is_running()

    def chat(self, *, system: str, user: str, temperature: float = 0.2, options: dict[str, Any] | None = None) -> str:
        return self.client.chat(system=system, user=user, temperature=temperature, options=options)

    def chat_stream(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.2,
        options: dict[str, Any] | None = None,
    ) -> Iterable[str]:
        return self.client.chat_stream(system=system, user=user, temperature=temperature, options=options)

    def embeddings(self, *, prompt: str, model: str | None = None) -> list[float]:
        return self.client.embeddings(prompt=prompt, model=model)
