from __future__ import annotations

import json

import pytest
import requests

from writing_agent.llm.provider import LLMProviderError
from writing_agent.llm.providers.openai_compatible_provider import OpenAICompatibleProvider


def _response(*, status: int, payload: dict) -> requests.Response:
    resp = requests.Response()
    resp.status_code = status
    resp._content = json.dumps(payload).encode("utf-8")
    resp.headers["content-type"] = "application/json"
    resp.encoding = "utf-8"
    return resp


def test_openai_provider_maps_quota_error_to_specific_code() -> None:
    resp = _response(
        status=429,
        payload={
            "error": {
                "message": "You exceeded your current quota, please check your plan and billing details.",
                "type": "insufficient_quota",
                "code": "insufficient_quota",
            }
        },
    )
    with pytest.raises(LLMProviderError, match="api_insufficient_quota:http_429"):
        OpenAICompatibleProvider._raise_http_error(resp)


def test_openai_provider_keeps_auth_failure_classification() -> None:
    resp = _response(status=401, payload={"error": {"message": "Unauthorized"}})
    with pytest.raises(LLMProviderError, match="api_auth_failed:http_401"):
        OpenAICompatibleProvider._raise_http_error(resp)
