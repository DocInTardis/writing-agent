from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

import writing_agent.web.app_v2 as app_v2


def _client() -> TestClient:
    return TestClient(app_v2.app)


def _disable_ollama(monkeypatch) -> None:
    monkeypatch.setattr(
        app_v2,
        "get_ollama_settings",
        lambda: SimpleNamespace(enabled=False, base_url="", model="", timeout_s=1.0),
    )


def test_doc_upload_rejects_unsupported_extension(monkeypatch):
    _disable_ollama(monkeypatch)
    session = app_v2.store.create()
    app_v2.store.put(session)
    client = _client()
    resp = client.post(
        f"/api/doc/{session.id}/upload",
        files={"file": ("payload.exe", b"MZ\x00\x02", "application/octet-stream")},
    )
    assert resp.status_code == 400
    assert "unsupported file type" in (resp.text or "")


def test_doc_upload_rejects_invalid_png_signature(monkeypatch):
    _disable_ollama(monkeypatch)
    session = app_v2.store.create()
    app_v2.store.put(session)
    client = _client()
    resp = client.post(
        f"/api/doc/{session.id}/upload",
        files={"file": ("bad.png", b"this is plain text, not png", "image/png")},
    )
    assert resp.status_code == 400
    assert "invalid image payload" in (resp.text or "")


def test_doc_upload_rejects_binary_payload_for_text(monkeypatch):
    _disable_ollama(monkeypatch)
    session = app_v2.store.create()
    app_v2.store.put(session)
    client = _client()
    resp = client.post(
        f"/api/doc/{session.id}/upload",
        files={"file": ("notes.txt", b"abc\x00def", "text/plain")},
    )
    assert resp.status_code == 400
    assert "invalid text payload" in (resp.text or "")


def test_doc_upload_accepts_valid_text_and_sanitizes_filename(monkeypatch):
    _disable_ollama(monkeypatch)
    session = app_v2.store.create()
    app_v2.store.put(session)
    client = _client()
    resp = client.post(
        f"/api/doc/{session.id}/upload",
        files={"file": ("../../safe-notes.txt", b"plain text upload content", "text/plain")},
    )
    assert resp.status_code == 200
    body = resp.json()
    item = body.get("item") if isinstance(body, dict) else {}
    assert isinstance(item, dict)
    assert item.get("source_name") == "safe-notes.txt"


def test_library_upload_accepts_valid_png(monkeypatch):
    _disable_ollama(monkeypatch)
    client = _client()
    png_bytes = b"\x89PNG\r\n\x1a\n" + (b"\x00" * 32)
    resp = client.post(
        "/api/library/upload",
        files={"file": ("figure.png", png_bytes, "image/png")},
    )
    assert resp.status_code == 200
    body = resp.json()
    item = body.get("item") if isinstance(body, dict) else {}
    assert isinstance(item, dict)
    assert item.get("source_name") == "figure.png"


def test_library_upload_rejects_invalid_png_signature(monkeypatch):
    _disable_ollama(monkeypatch)
    client = _client()
    resp = client.post(
        "/api/library/upload",
        files={"file": ("bad.png", b"this is plain text, not png", "image/png")},
    )
    assert resp.status_code == 400
    assert "invalid image payload" in (resp.text or "")


def test_library_upload_rejects_binary_payload_for_text(monkeypatch):
    _disable_ollama(monkeypatch)
    client = _client()
    resp = client.post(
        "/api/library/upload",
        files={"file": ("notes.txt", b"abc\x00def", "text/plain")},
    )
    assert resp.status_code == 400
    assert "invalid text payload" in (resp.text or "")
