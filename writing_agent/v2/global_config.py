"""Global config and normalized failure reasons for v2 runtime."""

from __future__ import annotations

import re

FAILURE_API_AUTH_FAILED = "api_auth_failed"
FAILURE_API_PROVIDER_UNREACHABLE = "api_provider_unreachable"
FAILURE_API_PROVIDER_MISCONFIGURED = "api_provider_misconfigured"
FAILURE_PROVIDER_DISABLED = "provider_disabled"
FAILURE_PROVIDER_UNSUPPORTED = "provider_unsupported"
FAILURE_PROVIDER_PRECHECK_FAILED = "provider_precheck_failed"

STEP1_PROVIDER_ERROR_CODES = frozenset(
    {
        FAILURE_API_AUTH_FAILED,
        FAILURE_API_PROVIDER_UNREACHABLE,
        FAILURE_API_PROVIDER_MISCONFIGURED,
        FAILURE_PROVIDER_DISABLED,
        FAILURE_PROVIDER_UNSUPPORTED,
        FAILURE_PROVIDER_PRECHECK_FAILED,
    }
)


def classify_provider_error(message: str) -> str:
    text = str(message or "").strip().lower()
    if not text:
        return FAILURE_PROVIDER_PRECHECK_FAILED
    if "missing writing_agent_openai_api_key" in text:
        return FAILURE_API_PROVIDER_MISCONFIGURED
    if "unsupported llm provider" in text:
        return FAILURE_PROVIDER_UNSUPPORTED
    if "provider disabled" in text or "llm provider disabled" in text:
        return FAILURE_PROVIDER_DISABLED
    if re.search(r"\b(401|403)\b", text) or "unauthorized" in text or "forbidden" in text:
        return FAILURE_API_AUTH_FAILED
    if re.search(r"\b(timeout|timed out|connection|unreachable|refused|dns)\b", text):
        return FAILURE_API_PROVIDER_UNREACHABLE
    return FAILURE_PROVIDER_PRECHECK_FAILED
