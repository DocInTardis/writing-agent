from __future__ import annotations

import asyncio
import json

import pytest

from writing_agent.web.services.version_service import VersionService


class _FakeHTTPException(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class _FakeRequest:
    def __init__(self, body: bytes) -> None:
        self._body = body

    async def body(self) -> bytes:
        return self._body


class _FakeAppV2:
    json = json
    HTTPException = _FakeHTTPException


def test_read_payload_returns_empty_dict_for_commit_mode_invalid_json() -> None:
    request = _FakeRequest(b"{")

    payload = asyncio.run(VersionService._read_payload(request, _FakeAppV2, raise_on_invalid=False))

    assert payload == {}


def test_read_payload_raises_http_exception_with_cause_on_invalid_json() -> None:
    request = _FakeRequest(b"{")

    with pytest.raises(_FakeHTTPException) as exc_info:
        asyncio.run(VersionService._read_payload(request, _FakeAppV2, raise_on_invalid=True))

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "invalid payload"
    assert isinstance(exc_info.value.__cause__, json.JSONDecodeError)


def test_read_payload_rejects_non_object_payload_when_strict() -> None:
    request = _FakeRequest(b"[]")

    with pytest.raises(_FakeHTTPException) as exc_info:
        asyncio.run(VersionService._read_payload(request, _FakeAppV2, raise_on_invalid=True))

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "invalid payload"
    assert exc_info.value.__cause__ is None
