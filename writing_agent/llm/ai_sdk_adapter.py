"""Ai Sdk Adapter module.

This module belongs to `writing_agent.llm` in the writing-agent codebase.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable

from writing_agent.llm.factory import get_default_provider


class AISDKError(RuntimeError):
    pass


class RateLimitError(AISDKError):
    pass


class TimeoutError(AISDKError):
    pass


class ContextOverflowError(AISDKError):
    pass


class SchemaValidationError(AISDKError):
    pass


@dataclass(frozen=True)
class ToolCall:
    name: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class StreamChunk:
    delta: str
    done: bool = False
    usage: dict[str, int] | None = None


def classify_error(exc: Exception) -> AISDKError:
    msg = str(exc or "").lower()
    if "rate" in msg and "limit" in msg:
        return RateLimitError(str(exc))
    if "timeout" in msg or "timed out" in msg:
        return TimeoutError(str(exc))
    if "context" in msg and "overflow" in msg:
        return ContextOverflowError(str(exc))
    if "schema" in msg or "json" in msg:
        return SchemaValidationError(str(exc))
    return AISDKError(str(exc))


class AISDKAdapter:
    """
    Minimal backend adapter exposing Vercel-AI-SDK-like semantics:
    - stream_text
    - generate_object
    - tool_call
    """

    def __init__(self, *, provider=None, fallback_provider=None) -> None:
        self.provider = provider or get_default_provider()
        self.fallback_provider = fallback_provider

    def stream_text(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.2,
        max_retries: int = 2,
        options: dict[str, Any] | None = None,
    ) -> Iterable[StreamChunk]:
        attempts = max(1, int(max_retries))
        last_exc: Exception | None = None
        for idx in range(1, attempts + 1):
            try:
                for delta in self.provider.chat_stream(
                    system=system,
                    user=user,
                    temperature=temperature,
                    options=options,
                ):
                    if delta:
                        yield StreamChunk(delta=str(delta), done=False)
                yield StreamChunk(delta="", done=True)
                return
            except Exception as exc:
                last_exc = classify_error(exc)
                if idx >= attempts:
                    break
                time.sleep(0.2 * idx)
                if self.fallback_provider is not None:
                    self.provider = self.fallback_provider
        raise last_exc or AISDKError("stream_text failed")

    def generate_object(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any] | None = None,
        schema_validator: Callable[[dict[str, Any]], bool] | None = None,
        temperature: float = 0.1,
        max_retries: int = 2,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        attempts = max(1, int(max_retries))
        last_exc: Exception | None = None
        for idx in range(1, attempts + 1):
            try:
                if hasattr(self.provider, "generate_object"):
                    payload = self.provider.generate_object(
                        system=system,
                        user=user,
                        schema=dict(schema or {}),
                        temperature=temperature,
                        options=options,
                    )
                else:
                    raw = self.provider.chat(system=system, user=user, temperature=temperature, options=options)
                    payload = _extract_json(raw)
                if not isinstance(payload, dict):
                    raise SchemaValidationError("generated object is not a json object")
                if schema_validator and not schema_validator(payload):
                    raise SchemaValidationError("schema validation failed")
                return payload
            except Exception as exc:
                last_exc = classify_error(exc)
                if idx >= attempts:
                    break
                time.sleep(0.2 * idx)
                if self.fallback_provider is not None:
                    self.provider = self.fallback_provider
        raise last_exc or AISDKError("generate_object failed")

    def tool_call(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        registry: dict[str, Callable[[dict[str, Any]], Any]],
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if hasattr(self.provider, "tool_call"):
            try:
                result = self.provider.tool_call(
                    tool_name=tool_name,
                    arguments=arguments,
                    options=options,
                )
                if isinstance(result, dict):
                    return result
                return {"ok": 1, "result": result}
            except Exception:
                pass
        fn = registry.get(str(tool_name))
        if fn is None:
            raise AISDKError(f"tool not found: {tool_name}")
        result = fn(dict(arguments or {}))
        if isinstance(result, dict):
            return result
        return {"ok": 1, "result": result}


def _extract_json(text: str) -> dict[str, Any] | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    if raw.startswith("```"):
        raw = raw.replace("```json", "").replace("```", "").strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(raw[start : end + 1])
    except Exception:
        return None
    return value if isinstance(value, dict) else None
