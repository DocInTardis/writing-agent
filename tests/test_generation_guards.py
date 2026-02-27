from __future__ import annotations

import time

from fastapi.testclient import TestClient

import writing_agent.web.app_v2 as app_v2
from writing_agent.models import Citation


def _client() -> TestClient:
    return TestClient(app_v2.app)


def test_compose_mode_helpers_cover_invalid_and_guard_text():
    assert app_v2._normalize_compose_mode("continue") == "continue"
    assert app_v2._normalize_compose_mode("OVERWRITE") == "overwrite"
    assert app_v2._normalize_compose_mode("something-else") == "auto"

    inst = "?????"
    guarded = app_v2._apply_compose_mode_instruction(inst, "continue", has_existing=True)
    assert "????" in guarded
    overwrite = app_v2._apply_compose_mode_instruction(inst, "overwrite", has_existing=True)
    assert "????" in overwrite


def test_save_settings_preserves_internal_generation_prefs():
    session = app_v2.store.create()
    session.generation_prefs = {
        "_wa_resume_state": {"status": "interrupted", "updated_at": time.time(), "user_instruction": "x"}
    }
    app_v2.store.put(session)

    client = _client()
    resp = client.post(
        f"/api/doc/{session.id}/settings",
        json={"generation_prefs": {"target_length_mode": "chars", "target_char_count": 1200}},
    )
    assert resp.status_code == 200

    saved = app_v2.store.get(session.id)
    assert saved is not None
    assert saved.generation_prefs.get("target_char_count") == 1200
    assert "_wa_resume_state" in saved.generation_prefs


def test_citation_verify_persists_summary_and_internal_state(monkeypatch):
    session = app_v2.store.create()
    session.citations = {
        "alpha": Citation(key="alpha", title="Alpha Study", authors="A", year="2024", venue="", url=""),
        "beta": Citation(key="beta", title="Beta Study", authors="B", year="2023", venue="", url=""),
    }
    app_v2.store.put(session)

    def _fake_verify(cite: Citation):
        if cite.key == "alpha":
            row = {
                "id": "alpha",
                "status": "verified",
                "provider": "crossref",
                "score": 0.91,
                "matched_title": cite.title,
                "matched_year": cite.year,
                "matched_source": "Journal",
            }
            return row, cite
        row = {
            "id": "beta",
            "status": "not_found",
            "provider": "",
            "score": 0.1,
            "matched_title": "",
            "matched_year": "",
            "matched_source": "",
        }
        return row, cite

    monkeypatch.setattr(app_v2, "_verify_one_citation", _fake_verify)

    client = _client()
    resp = client.post(f"/api/doc/{session.id}/citations/verify", json={"persist": True})
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("summary", {}).get("verified") == 1
    assert body.get("summary", {}).get("not_found") == 1

    saved = app_v2.store.get(session.id)
    assert saved is not None
    state = (saved.generation_prefs or {}).get("_wa_citation_verify")
    assert isinstance(state, dict)
    items = state.get("items") if isinstance(state, dict) else {}
    assert isinstance(items, dict)
    assert items.get("alpha", {}).get("status") == "verified"


def test_export_check_blocks_unverified_citation_when_marker_exists():
    session = app_v2.store.create()
    app_v2._set_doc_text(session, "# Title\n\n## Intro\nref [@alpha]\n\n## Method\ntext")
    session.citations = {
        "alpha": Citation(key="alpha", title="Alpha Study", authors="A", year="2024", venue="", url="")
    }
    session.generation_prefs = {
        "strict_citation_verify": True,
        "_wa_citation_verify": {
            "updated_at": time.time(),
            "items": {"alpha": {"status": "not_found", "score": 0.1}},
            "summary": {"total": 1, "verified": 0, "possible": 0, "not_found": 1, "error": 0},
        }
    }
    app_v2.store.put(session)

    client = _client()
    resp = client.get(f"/api/doc/{session.id}/export/check?format=docx&auto_fix=1")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("can_export") is False
    codes = {str(item.get("code") or "") for item in (body.get("issues") or []) if isinstance(item, dict)}
    assert "citation_unverified" in codes


def test_download_docx_rejects_when_unverified_citation():
    session = app_v2.store.create()
    app_v2._set_doc_text(session, "# Title\n\n## Intro\nref [@alpha]\n\n## End\nx")
    session.citations = {
        "alpha": Citation(key="alpha", title="Alpha Study", authors="A", year="2024", venue="", url="")
    }
    session.generation_prefs = {
        "strict_citation_verify": True,
        "_wa_citation_verify": {
            "updated_at": time.time(),
            "items": {"alpha": {"status": "not_found", "score": 0.1}},
            "summary": {"total": 1, "verified": 0, "possible": 0, "not_found": 1, "error": 0},
        }
    }
    app_v2.store.put(session)

    client = _client()
    resp = client.get(f"/download/{session.id}.docx")
    assert resp.status_code == 400
    assert "导出前校验未通过" in (resp.text or "")


def test_export_check_autofix_allows_export_for_missing_toc_and_reference():
    session = app_v2.store.create()
    app_v2._set_doc_text(session, "# Demo\n\n## Intro\ncontent\n\n## Method\nmore content")
    session.generation_prefs = {"strict_doc_format": True, "strict_citation_verify": False}
    app_v2.store.put(session)

    client = _client()
    resp = client.get(f"/api/doc/{session.id}/export/check?format=docx&auto_fix=1")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("can_export") is True
    warnings = body.get("warnings") or []
    assert any(str(w.get("code") or "") == "autofix_applied" for w in warnings if isinstance(w, dict))


def test_doc_api_exposes_resume_state_when_interrupted():
    session = app_v2.store.create()
    app_v2._set_doc_text(session, "# T\n\n## A\npartial")
    app_v2._update_resume_state(
        session,
        status="interrupted",
        user_instruction="continue writing",
        request_instruction="please continue writing",
        compose_mode="continue",
        partial_text=session.doc_text,
        error="stream interrupted",
    )
    app_v2.store.put(session)

    client = _client()
    resp = client.get(f"/api/doc/{session.id}")
    assert resp.status_code == 200
    body = resp.json()
    resume = body.get("resume_state")
    assert isinstance(resume, dict)
    assert resume.get("status") == "interrupted"
    assert resume.get("compose_mode") == "continue"


def test_generate_resume_sections_passed_to_graph(monkeypatch):
    session = app_v2.store.create()
    app_v2._set_doc_text(session, "# Title\n\n## Intro\nbase")
    session.template_required_h2 = ["Intro", "Methods"]
    session.template_outline = [(1, "Intro"), (1, "Methods")]
    app_v2.store.put(session)

    seen: dict[str, object] = {}
    quick_called = {"n": 0}

    monkeypatch.setattr(app_v2, "_ensure_ollama_ready", lambda: (True, ""))

    def _quick(*_args, **_kwargs):
        quick_called["n"] += 1
        return None

    monkeypatch.setattr(app_v2, "_try_quick_edit", _quick)
    monkeypatch.setattr(app_v2, "_run_message_analysis", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(app_v2, "_try_ai_intent_edit", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app_v2, "_should_route_to_revision", lambda *_args, **_kwargs: False)
    monkeypatch.setattr(app_v2, "_should_use_fast_generate", lambda *_args, **_kwargs: False)

    def _fake_graph(**kwargs):
        seen["required_h2"] = list(kwargs.get("required_h2") or [])
        seen["required_outline"] = list(kwargs.get("required_outline") or [])
        yield {"event": "plan", "sections": ["Intro", "Methods"]}
        yield {"event": "section", "phase": "end", "section": "Methods"}
        yield {"event": "final", "text": "# Title\n\n## Methods\nresumed output", "problems": []}

    monkeypatch.setattr(app_v2, "run_generate_graph", _fake_graph)

    client = _client()
    resp = client.post(
        f"/api/doc/{session.id}/generate",
        json={
            "instruction": "continue",
            "text": session.doc_text,
            "compose_mode": "continue",
            "resume_sections": ["Methods"],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("ok") == 1
    assert seen.get("required_h2") == ["Methods"]
    assert seen.get("required_outline") == []
    assert quick_called["n"] == 0


def test_export_check_warn_policy_allows_export_with_non_blocking_issues():
    session = app_v2.store.create()
    app_v2._set_doc_text(session, "# Title\n\n## Intro\nref [@alpha]\n\n## Method\ntext")
    session.citations = {
        "alpha": Citation(key="alpha", title="Alpha Study", authors="A", year="2024", venue="", url="")
    }
    session.generation_prefs = {
        "export_gate_policy": "warn",
        "strict_citation_verify": True,
        "_wa_citation_verify": {
            "updated_at": time.time(),
            "items": {"alpha": {"status": "not_found", "score": 0.1}},
            "summary": {"total": 1, "verified": 0, "possible": 0, "not_found": 1, "error": 0},
        },
    }
    app_v2.store.put(session)

    client = _client()
    resp = client.get(f"/api/doc/{session.id}/export/check?format=docx&auto_fix=1")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("policy") == "warn"
    assert body.get("can_export") is True
    issues = [x for x in (body.get("issues") or []) if isinstance(x, dict)]
    assert any(str(x.get("code") or "") == "citation_unverified" for x in issues)
    assert all(bool(x.get("blocking")) is False for x in issues)
    warnings = [x for x in (body.get("warnings") or []) if isinstance(x, dict)]
    assert any(str(x.get("code") or "") == "policy_warn" for x in warnings)


def test_export_check_off_policy_never_blocks():
    session = app_v2.store.create()
    app_v2._set_doc_text(session, "# Demo\n\n## Intro\ncontent\n\n## Method\nmore")
    session.generation_prefs = {"export_gate_policy": "off", "strict_doc_format": True}
    app_v2.store.put(session)

    client = _client()
    resp = client.get(f"/api/doc/{session.id}/export/check?format=docx&auto_fix=0")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("policy") == "off"
    assert body.get("can_export") is True
    issues = [x for x in (body.get("issues") or []) if isinstance(x, dict)]
    assert issues
    assert all(bool(x.get("blocking")) is False for x in issues)


def test_export_check_default_non_strict_mode_does_not_force_structure():
    session = app_v2.store.create()
    app_v2._set_doc_text(session, "# Demo\n\n## Intro\ncontent\n\n## Method\nmore")
    session.generation_prefs = {}
    app_v2.store.put(session)

    client = _client()
    resp = client.get(f"/api/doc/{session.id}/export/check?format=docx&auto_fix=1")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("can_export") is True
    issues = [x for x in (body.get("issues") or []) if isinstance(x, dict)]
    warnings = [x for x in (body.get("warnings") or []) if isinstance(x, dict)]
    issue_codes = {str(x.get("code") or "") for x in issues}
    warning_codes = {str(x.get("code") or "") for x in warnings}
    assert "missing_toc" not in issue_codes
    assert "missing_references" not in issue_codes
    assert "autofix_applied" not in warning_codes
