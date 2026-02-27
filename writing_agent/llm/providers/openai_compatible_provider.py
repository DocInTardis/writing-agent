"""Openai Compatible Provider module.

This module belongs to `writing_agent.llm.providers` in the writing-agent codebase.
"""

from __future__ import annotations

import json
import os
from typing import Any, Iterable

import requests

from writing_agent.llm.provider import LLMProvider, LLMProviderError


class OpenAICompatibleProvider(LLMProvider):
    def __init__(self, *, base_url: str, api_key: str, model: str, timeout_s: float = 60.0) -> None:
        self.base_url = str(base_url).rstrip("/")
        self.api_key = str(api_key)
        self.model = str(model)
        self.timeout_s = float(timeout_s)

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def is_running(self) -> bool:
        if not self.base_url or not self.api_key:
            return False
        try:
            resp = requests.get(f"{self.base_url}/models", headers=self._headers(), timeout=self.timeout_s)
            return resp.status_code < 500
        except Exception:
            return False

    def chat(self, *, system: str, user: str, temperature: float = 0.2, options: dict[str, Any] | None = None) -> str:
        payload = {
            "model": self.model,
            "temperature": float(temperature),
            "messages": [
                {"role": "system", "content": str(system or "")},
                {"role": "user", "content": str(user or "")},
            ],
            "stream": False,
        }
        if isinstance(options, dict):
            payload.update(options)
        url = f"{self.base_url}/chat/completions"
        try:
            resp = requests.post(url, headers=self._headers(), json=payload, timeout=self.timeout_s)
            resp.raise_for_status()
            raw = resp.json()
        except Exception as exc:
            raise LLMProviderError(str(exc)) from exc

        choices = raw.get("choices") if isinstance(raw, dict) else []
        if isinstance(choices, list) and choices:
            first = choices[0] if isinstance(choices[0], dict) else {}
            msg = first.get("message") if isinstance(first.get("message"), dict) else {}
            return str(msg.get("content") or "")
        return ""

    def chat_stream(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.2,
        options: dict[str, Any] | None = None,
    ) -> Iterable[str]:
        payload = {
            "model": self.model,
            "temperature": float(temperature),
            "messages": [
                {"role": "system", "content": str(system or "")},
                {"role": "user", "content": str(user or "")},
            ],
            "stream": True,
        }
        if isinstance(options, dict):
            payload.update(options)
        url = f"{self.base_url}/chat/completions"
        try:
            with requests.post(url, headers=self._headers(), json=payload, timeout=self.timeout_s, stream=True) as resp:
                resp.raise_for_status()
                for raw in resp.iter_lines(decode_unicode=True):
                    line = str(raw or "").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        obj = json.loads(data)
                    except Exception:
                        continue
                    choices = obj.get("choices") if isinstance(obj, dict) else []
                    if not isinstance(choices, list) or not choices:
                        continue
                    delta = choices[0].get("delta") if isinstance(choices[0], dict) else {}
                    if isinstance(delta, dict):
                        text = str(delta.get("content") or "")
                        if text:
                            yield text
        except Exception as exc:
            raise LLMProviderError(str(exc)) from exc

    def embeddings(self, *, prompt: str, model: str | None = None) -> list[float]:
        em_model = str(model or self.model)
        payload = {"model": em_model, "input": str(prompt or "")}
        url = f"{self.base_url}/embeddings"
        try:
            resp = requests.post(url, headers=self._headers(), json=payload, timeout=self.timeout_s)
            resp.raise_for_status()
            raw = resp.json()
        except Exception as exc:
            raise LLMProviderError(str(exc)) from exc
        data = raw.get("data") if isinstance(raw, dict) else []
        if isinstance(data, list) and data:
            first = data[0] if isinstance(data[0], dict) else {}
            emb = first.get("embedding")
            if isinstance(emb, list):
                return [float(x) for x in emb]
        return []


def from_env(*, model: str | None = None, timeout_s: float | None = None) -> OpenAICompatibleProvider:
    base = str(os.environ.get("WRITING_AGENT_OPENAI_BASE_URL", "https://api.openai.com/v1")).strip()
    key = str(os.environ.get("WRITING_AGENT_OPENAI_API_KEY", "")).strip()
    m = str(model or os.environ.get("WRITING_AGENT_OPENAI_MODEL", "gpt-4o-mini")).strip()
    t = float(timeout_s if timeout_s is not None else float(os.environ.get("WRITING_AGENT_OPENAI_TIMEOUT_S", "60")))
    if not key:
        raise LLMProviderError("missing WRITING_AGENT_OPENAI_API_KEY")
    return OpenAICompatibleProvider(base_url=base, api_key=key, model=m, timeout_s=t)
