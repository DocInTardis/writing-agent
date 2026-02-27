"""Node AI Gateway Provider module.

This module belongs to `writing_agent.llm.providers` in the writing-agent codebase.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import requests

from writing_agent.llm.provider import LLMProvider, LLMProviderError


def _bool_env(raw: str | None, default: bool) -> bool:
    text = str(raw or "").strip().lower()
    if not text:
        return bool(default)
    return text in {"1", "true", "yes", "on"}


def _safe_json(resp: requests.Response) -> dict[str, Any]:
    try:
        value = resp.json()
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _sanitize_gateway_error(payload: dict[str, Any], status_code: int) -> str:
    err = payload.get("error") if isinstance(payload.get("error"), dict) else {}
    code = str(err.get("code") or "PROVIDER_ERROR")
    if code == "RATE_LIMIT":
        return "node_gateway: rate limited"
    if code == "TIMEOUT":
        return "node_gateway: timeout"
    if code == "CONTEXT_OVERFLOW":
        return "node_gateway: context overflow"
    if code == "SCHEMA_FAIL":
        return "node_gateway: schema validation failed"
    if 400 <= int(status_code or 0) < 500:
        return "node_gateway: bad request"
    return "node_gateway: upstream provider error"


@dataclass(frozen=True)
class NodeGatewayConfig:
    gateway_url: str
    model: str
    timeout_s: float = 60.0
    max_retries: int = 2
    auto_fallback: bool = True


class NodeAIGatewayProvider(LLMProvider):
    """LLM provider implementation backed by the Node AI Gateway HTTP service."""

    def __init__(self, *, config: NodeGatewayConfig, fallback_provider: LLMProvider | None = None) -> None:
        self.config = config
        self.fallback_provider = fallback_provider
        self._base = str(config.gateway_url or "").rstrip("/")
        self._timeout = float(config.timeout_s)
        self._retries = max(1, int(config.max_retries))

    def _headers(self, options: dict[str, Any] | None) -> dict[str, str]:
        opts = options or {}
        headers = {"Content-Type": "application/json"}
        trace_id = str(opts.get("trace_id") or opts.get("correlation_id") or "").strip()
        if trace_id:
            headers["x-trace-id"] = trace_id
        idempotency_key = str(opts.get("idempotency_key") or "").strip()
        if idempotency_key:
            headers["x-idempotency-key"] = idempotency_key
        return headers

    def _request_json(self, *, path: str, payload: dict[str, Any], options: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self._base}{path}"
        last_error: Exception | None = None
        for _ in range(self._retries):
            try:
                resp = requests.post(url, headers=self._headers(options), json=payload, timeout=self._timeout)
                if resp.status_code >= 400:
                    data = _safe_json(resp)
                    raise LLMProviderError(_sanitize_gateway_error(data, resp.status_code))
                data = _safe_json(resp)
                if not isinstance(data, dict) or not data.get("ok"):
                    raise LLMProviderError("node_gateway: malformed response")
                return data
            except Exception as exc:
                last_error = exc
        raise LLMProviderError(str(last_error or "node_gateway request failed"))

    def _with_fallback(self, fn, fallback_fn):
        try:
            return fn()
        except Exception as exc:
            if self.config.auto_fallback and self.fallback_provider is not None and callable(fallback_fn):
                self._record_fallback_event(reason=str(exc))
                return fallback_fn()
            raise LLMProviderError(str(exc)) from exc

    def _record_fallback_event(self, *, reason: str) -> None:
        path = Path(str(os.environ.get("WRITING_AGENT_NODE_FALLBACK_LOG", ".data/metrics/node_backend_fallback.jsonl")).strip())
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "ts": time.time(),
            "event": "node_backend_fallback",
            "reason": str(reason or "")[:240],
        }
        try:
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception:
            return

    def is_running(self) -> bool:
        if not self._base:
            return False
        try:
            resp = requests.get(f"{self._base}/health", timeout=min(5.0, self._timeout))
            return 200 <= resp.status_code < 300
        except Exception:
            return False

    def chat(self, *, system: str, user: str, temperature: float = 0.2, options: dict[str, Any] | None = None) -> str:
        payload = {
            "system": str(system or ""),
            "prompt": str(user or ""),
            "model": self.config.model,
            "temperature": float(temperature),
            "stream": False,
            "max_retries": self._retries,
            "timeout_ms": int(self._timeout * 1000),
        }

        def _call():
            data = self._request_json(path="/v1/stream-text", payload=payload, options=options)
            return str(data.get("text") or "")

        def _fallback():
            if not self.fallback_provider:
                raise LLMProviderError("fallback provider unavailable")
            return self.fallback_provider.chat(system=system, user=user, temperature=temperature, options=options)

        return self._with_fallback(_call, _fallback)

    def chat_stream(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.2,
        options: dict[str, Any] | None = None,
    ) -> Iterable[str]:
        payload = {
            "system": str(system or ""),
            "prompt": str(user or ""),
            "model": self.config.model,
            "temperature": float(temperature),
            "stream": True,
            "max_retries": self._retries,
            "timeout_ms": int(self._timeout * 1000),
        }

        def _iter_gateway() -> Iterable[str]:
            url = f"{self._base}/v1/stream-text"
            with requests.post(
                url,
                headers=self._headers(options),
                json=payload,
                timeout=self._timeout,
                stream=True,
            ) as resp:
                if resp.status_code >= 400:
                    data = _safe_json(resp)
                    raise LLMProviderError(_sanitize_gateway_error(data, resp.status_code))
                for raw in resp.iter_lines(decode_unicode=True):
                    line = str(raw or "").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    json_part = line[5:].strip()
                    try:
                        event = json.loads(json_part)
                    except Exception:
                        continue
                    kind = str(event.get("type") or "")
                    if kind == "text-delta":
                        delta = str(event.get("delta") or "")
                        if delta:
                            yield delta
                    elif kind == "error":
                        event_payload = event if isinstance(event, dict) else {}
                        raise LLMProviderError(_sanitize_gateway_error(event_payload, 500))
                    elif kind == "done":
                        break

        try:
            yield from _iter_gateway()
        except Exception as exc:
            if self.config.auto_fallback and self.fallback_provider is not None:
                self._record_fallback_event(reason=str(exc))
                yield from self.fallback_provider.chat_stream(
                    system=system,
                    user=user,
                    temperature=temperature,
                    options=options,
                )
                return
            raise LLMProviderError(str(exc)) from exc

    def embeddings(self, *, prompt: str, model: str | None = None) -> list[float]:
        if self.fallback_provider is not None:
            return self.fallback_provider.embeddings(prompt=prompt, model=model)
        return []

    def generate_object(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        temperature: float = 0.1,
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "system": str(system or ""),
            "prompt": str(user or ""),
            "schema": dict(schema or {}),
            "model": self.config.model,
            "temperature": float(temperature),
            "max_retries": self._retries,
            "timeout_ms": int(self._timeout * 1000),
        }

        def _call():
            data = self._request_json(path="/v1/generate-object", payload=payload, options=options)
            obj = data.get("object")
            if not isinstance(obj, dict):
                raise LLMProviderError("node_gateway: object payload is not a json object")
            return obj

        def _fallback():
            if self.fallback_provider is None or not hasattr(self.fallback_provider, "chat"):
                raise LLMProviderError("fallback provider unavailable")
            raw = self.fallback_provider.chat(system=system, user=user, temperature=temperature, options=options)
            try:
                parsed = json.loads(str(raw or ""))
            except Exception as exc:
                raise LLMProviderError("fallback schema parse failed") from exc
            if not isinstance(parsed, dict):
                raise LLMProviderError("fallback schema parse failed")
            return parsed

        return self._with_fallback(_call, _fallback)

    def tool_call(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        options: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = {
            "tool_name": str(tool_name or ""),
            "arguments": dict(arguments or {}),
            "model": self.config.model,
        }

        def _call():
            data = self._request_json(path="/v1/tool-call", payload=payload, options=options)
            result = data.get("result")
            return result if isinstance(result, dict) else {"ok": 1, "result": result}

        def _fallback():
            return {"ok": 0, "error": "tool fallback unavailable"}

        return self._with_fallback(_call, _fallback)


def from_env(*, model: str | None = None, timeout_s: float | None = None, fallback_provider: LLMProvider | None = None) -> NodeAIGatewayProvider:
    import os

    gateway_url = str(os.environ.get("WRITING_AGENT_NODE_GATEWAY_URL", "")).strip()
    if not gateway_url:
        raise LLMProviderError("missing WRITING_AGENT_NODE_GATEWAY_URL")
    chosen_model = str(model or os.environ.get("WA_NODE_GATEWAY_MODEL") or os.environ.get("WRITING_AGENT_OPENAI_MODEL", "gpt-4o-mini")).strip()
    chosen_timeout = float(timeout_s if timeout_s is not None else float(os.environ.get("WA_NODE_GATEWAY_TIMEOUT_S", "60")))
    max_retries = int(os.environ.get("WA_NODE_GATEWAY_MAX_RETRIES", "2"))
    auto_fallback = _bool_env(os.environ.get("WRITING_AGENT_NODE_GATEWAY_AUTO_FALLBACK"), True)
    config = NodeGatewayConfig(
        gateway_url=gateway_url,
        model=chosen_model,
        timeout_s=chosen_timeout,
        max_retries=max_retries,
        auto_fallback=auto_fallback,
    )
    return NodeAIGatewayProvider(config=config, fallback_provider=fallback_provider)
