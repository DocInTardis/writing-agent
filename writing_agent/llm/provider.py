"""Provider module.

This module belongs to `writing_agent.llm` in the writing-agent codebase.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Iterable


class LLMProviderError(RuntimeError):
    pass


class LLMProvider(ABC):
    @abstractmethod
    def is_running(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def chat(self, *, system: str, user: str, temperature: float = 0.2, options: dict[str, Any] | None = None) -> str:
        raise NotImplementedError

    @abstractmethod
    def chat_stream(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.2,
        options: dict[str, Any] | None = None,
    ) -> Iterable[str]:
        raise NotImplementedError

    @abstractmethod
    def embeddings(self, *, prompt: str, model: str | None = None) -> list[float]:
        raise NotImplementedError
