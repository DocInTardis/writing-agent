"""Openai Compatible Provider module.

This module belongs to `writing_agent.llm.providers` in the writing-agent codebase.
"""

from __future__ import annotations

import logging
logger = logging.getLogger(__name__)

import json
import os
from collections.abc import Iterable
from typing import Any

import requests

from writing_agent.llm.provider import LLMProvider, LLMProviderError
from writing_agent.llm.openai_config import resolve_openai_candidates, resolve_openai_primary
from writing_agent.llm.providers._sse import iter_sse_data_lines, repair_utf8_mojibake


def _http_pool_size() -> int:
    raw = str(os.environ.get("WRITING_AGENT_HTTP_POOL_SIZE", "16")).strip()
    try:
        return max(4, int(raw))
    except Exception:
        return 16


def _build_session() -> requests.Session:
    session = requests.Session()
    try:
        pool = _http_pool_size()
        adapter = requests.adapters.HTTPAdapter(pool_connections=pool, pool_maxsize=pool, max_retries=0)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
    except Exception as _exc:
        logger.debug("Ignored error in openai_compatible_provider.py: %s", _exc, exc_info=True)

    return session



def _error_payload_text(resp: requests.Response) -> str:
    pieces: list[str] = []
    try:
        payload = resp.json()
    except Exception:
        payload = None
    if isinstance(payload, dict):
        err = payload.get("error")
        if isinstance(err, dict):
            for key in ("type", "code", "message"):
                value = str(err.get(key) or "").strip()
                if value:
                    pieces.append(value)
        elif err:
            pieces.append(str(err))
        for key in ("message", "detail"):
            value = str(payload.get(key) or "").strip()
            if value:
                pieces.append(value)
    text = " ".join(piece for piece in pieces if piece).strip()
    if text:
        return text.lower()
    try:
        return str(resp.text or "").strip().lower()
    except Exception:
        return ""


def _looks_like_quota_error(*, status: int, payload_text: str) -> bool:
    if int(status or 0) not in {403, 429}:
        return False
    text = str(payload_text or "").strip().lower()
    if not text:
        return False
    return any(
        token in text
        for token in (
            "insufficient_quota",
            "quota exceeded",
            "quota_exceeded",
            "exceeded your current quota",
            "billing_hard_limit",
            "billing hard limit",
            "hard limit reached",
            "credit balance is too low",
        )
    )


class OpenAICompatibleProvider(LLMProvider):
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout_s: float = 60.0,
        wire_api: str = "chat_completions",
    ) -> None:
        self.base_url = str(base_url).rstrip("/")
        self.api_key = str(api_key)
        self.model = str(model)
        self.timeout_s = float(timeout_s)
        self.wire_api = str(wire_api or "chat_completions").strip().lower() or "chat_completions"
        self._session = _build_session()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _raise_http_error(resp: requests.Response) -> None:
        if resp.status_code < 400:
            return
        status = int(resp.status_code)
        payload_text = _error_payload_text(resp)
        if _looks_like_quota_error(status=status, payload_text=payload_text):
            raise LLMProviderError(f"api_insufficient_quota:http_{status}")
        if status in {401, 403}:
            raise LLMProviderError(f"api_auth_failed:http_{status}")
        if status in {408, 429, 500, 502, 503, 504}:
            raise LLMProviderError(f"api_provider_unreachable:http_{status}")
        raise LLMProviderError(f"api_provider_request_failed:http_{status}")

    def is_running(self) -> bool:
        if not self.base_url or not self.api_key:
            return False
        try:
            resp = self._session.get(f"{self.base_url}/models", headers=self._headers(), timeout=self.timeout_s)
            return resp.status_code < 500
        except Exception:
            return False

    @staticmethod
    def _translate_options(options: dict[str, Any] | None, *, wire_api: str) -> dict[str, Any]:
        if not isinstance(options, dict):
            return {}
        translated = dict(options)
        if wire_api == "responses":
            num_predict = translated.pop("num_predict", None)
            if num_predict is not None and "max_output_tokens" not in translated:
                try:
                    translated["max_output_tokens"] = max(1, int(num_predict))
                except Exception as _exc:
                    logger.debug("Ignored error in openai_compatible_provider.py: %s", _exc, exc_info=True)

        return translated

    def _responses_payload(self, *, system: str, user: str, temperature: float, options: dict[str, Any] | None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "input": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": str(user or ""),
                        }
                    ],
                }
            ],
        }
        if str(system or "").strip():
            payload["instructions"] = str(system or "")
        if temperature is not None:
            payload["temperature"] = float(temperature)
        payload.update(self._translate_options(options, wire_api="responses"))
        return payload

    @staticmethod
    def _extract_response_text(raw: dict[str, Any]) -> str:
        direct = repair_utf8_mojibake(str(raw.get("output_text") or ""))
        if direct:
            return direct
        output = raw.get("output")
        if not isinstance(output, list):
            return ""
        chunks: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if not isinstance(part, dict):
                    continue
                if str(part.get("type") or "").strip().lower() not in {"output_text", "text"}:
                    continue
                text = repair_utf8_mojibake(str(part.get("text") or ""))
                if text:
                    chunks.append(text)
        return "".join(chunks)

    def chat(self, *, system: str, user: str, temperature: float = 0.2, options: dict[str, Any] | None = None) -> str:
        if self.wire_api == "responses":
            payload = self._responses_payload(system=system, user=user, temperature=temperature, options=options)
            url = f"{self.base_url}/responses"
            try:
                resp = self._session.post(url, headers=self._headers(), json=payload, timeout=self.timeout_s)
                self._raise_http_error(resp)
                raw = resp.json()
            except Exception as exc:
                raise LLMProviderError(str(exc)) from exc
            return self._extract_response_text(raw if isinstance(raw, dict) else {})
        payload = {
            "model": self.model,
            "temperature": float(temperature),
            "messages": [
                {"role": "system", "content": str(system or "")},
                {"role": "user", "content": str(user or "")},
            ],
            "stream": False,
        }
        payload.update(self._translate_options(options, wire_api="chat_completions"))
        url = f"{self.base_url}/chat/completions"
        try:
            resp = self._session.post(url, headers=self._headers(), json=payload, timeout=self.timeout_s)
            self._raise_http_error(resp)
            raw = resp.json()
        except Exception as exc:
            raise LLMProviderError(str(exc)) from exc

        choices = raw.get("choices") if isinstance(raw, dict) else []
        if isinstance(choices, list) and choices:
            first = choices[0] if isinstance(choices[0], dict) else {}
            msg = first.get("message") if isinstance(first.get("message"), dict) else {}
            return repair_utf8_mojibake(str(msg.get("content") or ""))
        return ""

    def chat_stream(
        self,
        *,
        system: str,
        user: str,
        temperature: float = 0.2,
        options: dict[str, Any] | None = None,
    ) -> Iterable[str]:
        if self.wire_api == "responses":
            payload = self._responses_payload(system=system, user=user, temperature=temperature, options=options)
            payload["stream"] = True
            url = f"{self.base_url}/responses"
            try:
                with self._session.post(url, headers=self._headers(), json=payload, timeout=self.timeout_s, stream=True) as resp:
                    self._raise_http_error(resp)
                    emitted = False
                    for data in iter_sse_data_lines(resp):
                        if data == "[DONE]":
                            break
                        try:
                            obj = json.loads(data)
                        except Exception:
                            continue
                        if not isinstance(obj, dict):
                            continue
                        event_type = str(obj.get("type") or "").strip().lower()
                        if event_type == "response.output_text.delta":
                            text = repair_utf8_mojibake(str(obj.get("delta") or ""))
                            if text:
                                emitted = True
                                yield text
                        elif event_type == "response.completed" and not emitted:
                            response = obj.get("response")
                            if isinstance(response, dict):
                                text = self._extract_response_text(response)
                                if text:
                                    yield text
            except Exception as exc:
                raise LLMProviderError(str(exc)) from exc
            return
        payload = {
            "model": self.model,
            "temperature": float(temperature),
            "messages": [
                {"role": "system", "content": str(system or "")},
                {"role": "user", "content": str(user or "")},
            ],
            "stream": True,
        }
        payload.update(self._translate_options(options, wire_api="chat_completions"))
        url = f"{self.base_url}/chat/completions"
        try:
            with self._session.post(url, headers=self._headers(), json=payload, timeout=self.timeout_s, stream=True) as resp:
                self._raise_http_error(resp)
                for data in iter_sse_data_lines(resp):
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
                        text = repair_utf8_mojibake(str(delta.get("content") or ""))
                        if text:
                            yield text
        except Exception as exc:
            raise LLMProviderError(str(exc)) from exc

    def embeddings(self, *, prompt: str, model: str | None = None) -> list[float]:
        em_model = str(model or self.model)
        payload = {"model": em_model, "input": str(prompt or "")}
        url = f"{self.base_url}/embeddings"
        try:
            resp = self._session.post(url, headers=self._headers(), json=payload, timeout=self.timeout_s)
            self._raise_http_error(resp)
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
    cfg = resolve_openai_primary(model=model, timeout_s=timeout_s)
    if cfg is None:
        raise LLMProviderError("missing WRITING_AGENT_OPENAI_API_KEY")
    return OpenAICompatibleProvider(
        base_url=cfg.base_url,
        api_key=cfg.api_key,
        model=cfg.model,
        timeout_s=cfg.timeout_s,
        wire_api=cfg.wire_api,
    )


def providers_from_env(*, model: str | None = None, timeout_s: float | None = None) -> list[OpenAICompatibleProvider]:
    providers: list[OpenAICompatibleProvider] = []
    for cfg in resolve_openai_candidates(model=model, timeout_s=timeout_s):
        providers.append(
            OpenAICompatibleProvider(
                base_url=cfg.base_url,
                api_key=cfg.api_key,
                model=cfg.model,
                timeout_s=cfg.timeout_s,
                wire_api=cfg.wire_api,
            )
        )
    return providers
