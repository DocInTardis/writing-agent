from __future__ import annotations

import asyncio
import json
import time
import uuid
from types import SimpleNamespace

import pytest

from writing_agent.storage import DocSession, VersionNode
from writing_agent.web.domains.version_state_domain import auto_commit_version, get_current_branch
from writing_agent.web.services import version_service
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


def _session():
    return DocSession(id="test", doc_text="original", doc_ir={"blocks": [{"text": "original"}]})


def _app(monkeypatch, session):
    app = SimpleNamespace(
        store=SimpleNamespace(get=lambda _: session, put=lambda _: None),
        json=json,
        uuid=uuid,
        time=time,
        VersionNode=VersionNode,
        HTTPException=_FakeHTTPException,
        _get_current_branch=get_current_branch,
    )
    monkeypatch.setattr(version_service, "app_v2_module", lambda: app)


def test_commit_and_checkout_isolate_nested_document(monkeypatch):
    session = _session()
    _app(monkeypatch, session)
    service = VersionService()
    result = asyncio.run(service.version_commit(session.id, _FakeRequest(b"{}")))
    version = session.versions[result["version_id"]]
    session.doc_ir["blocks"][0]["text"] = "edited"
    assert version.doc_ir["blocks"][0]["text"] == "original"

    request = _FakeRequest(json.dumps({"version_id": version.version_id}).encode())
    asyncio.run(service.version_checkout(session.id, request))
    assert session.doc_ir == version.doc_ir
    session.doc_ir["blocks"][0]["text"] = "edited after restore"
    assert version.doc_ir["blocks"][0]["text"] == "original"


def test_auto_commit_isolates_snapshot_and_skips_unchanged_content():
    session = _session()
    options = dict(
        author="test",
        tags=[],
        get_current_branch_fn=get_current_branch,
        version_node_cls=VersionNode,
        version_id_factory=lambda: uuid.uuid4().hex,
        now_ts=time.time,
    )
    first = auto_commit_version(session, "first", **options)
    assert auto_commit_version(session, "unchanged", **options) is None
    session.doc_ir["blocks"][0]["text"] = "format-only change"
    second = auto_commit_version(session, "second", **options)
    assert second is not None and second != first
    assert session.versions[first].doc_ir["blocks"][0]["text"] == "original"
    session.doc_ir["blocks"][0]["text"] = "next"
    assert session.versions[second].doc_ir["blocks"][0]["text"] == "format-only change"
