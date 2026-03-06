from __future__ import annotations

import re
import time

from fastapi.testclient import TestClient

import writing_agent.web.app_v2 as app_v2
from writing_agent.agents.citations import CitationAgent
from writing_agent.models import Citation, CitationStyle


def _client() -> TestClient:
    return TestClient(app_v2.app)


def test_citation_agent_formats_gbt_online_reference() -> None:
    cite = Citation(
        key="openai-2024",
        title="Structured Outputs",
        authors="OpenAI",
        year="2024",
        venue="",
        url="https://platform.openai.com/docs/guides/structured-output",
    )
    ref = CitationAgent().format_reference(cite, CitationStyle.GBT)
    assert "[EB/OL]" in ref
    assert "https://platform.openai.com/docs/guides/structured-output" in ref
    assert re.search(r"\[(?:19|20)\d{2}-\d{2}-\d{2}\]", ref) is not None


def test_citation_agent_formats_gbt_journal_reference() -> None:
    cite = Citation(
        key="smith-2022",
        title="A Survey on Writing Agents",
        authors="Smith J",
        year="2022",
        venue="Journal of Intelligent Systems",
        url="",
    )
    ref = CitationAgent().format_reference(cite, CitationStyle.GBT)
    assert "[J]" in ref
    assert "Journal of Intelligent Systems, 2022." in ref


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
    # Text-TOC insertion is no longer mandatory by default for DOCX export,
    # so autofix warning may or may not appear depending on what changed.
    assert isinstance(body.get("warnings") or [], list)


def test_export_check_blocks_missing_abstract_keywords_for_academic_doc() -> None:
    session = app_v2.store.create()
    text = "\n".join(
        [
            "# Thesis Title",
            "",
            "## 1 Introduction",
            "",
            ("content " * 260).strip(),
            "",
            "## 2 Method",
            "",
            ("details " * 260).strip(),
            "",
            "## References",
            "",
            "[1] A. Ref. 2024. https://example.com/1",
            "[2] B. Ref. 2024. https://example.com/2",
            "[3] C. Ref. 2024. https://example.com/3",
            "[4] D. Ref. 2024. https://example.com/4",
            "[5] E. Ref. 2024. https://example.com/5",
            "[6] F. Ref. 2024. https://example.com/6",
            "[7] G. Ref. 2024. https://example.com/7",
            "[8] H. Ref. 2024. https://example.com/8",
        ]
    )
    app_v2._set_doc_text(session, text)
    session.generation_prefs = {"strict_doc_format": True, "strict_citation_verify": False, "purpose": "undergraduate thesis"}
    app_v2.store.put(session)

    client = _client()
    resp = client.get(f"/api/doc/{session.id}/export/check?format=docx&auto_fix=0")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("can_export") is False
    codes = {str(item.get("code") or "") for item in (body.get("issues") or []) if isinstance(item, dict)}
    assert "missing_abstract" in codes
    assert "missing_keywords" in codes


def test_export_check_blocks_figure_table_mentions_without_objects() -> None:
    session = app_v2.store.create()
    text = "\n".join(
        [
            "# Thesis Title",
            "",
            "## 摘要",
            "",
            ("这是一段摘要内容。" * 80),
            "",
            "## 关键词",
            "",
            "写作代理；DocIR；路由",
            "",
            "## 1 引言",
            "",
            ("如图1所示，系统采用四层架构。如表1所示，指标对比如下。" * 40),
            "",
            "## 参考文献",
            "",
            "[1] A. Ref. 2024. https://example.com/1",
            "[2] B. Ref. 2024. https://example.com/2",
            "[3] C. Ref. 2024. https://example.com/3",
            "[4] D. Ref. 2024. https://example.com/4",
            "[5] E. Ref. 2024. https://example.com/5",
            "[6] F. Ref. 2024. https://example.com/6",
            "[7] G. Ref. 2024. https://example.com/7",
            "[8] H. Ref. 2024. https://example.com/8",
        ]
    )
    app_v2._set_doc_text(session, text)
    session.generation_prefs = {"strict_doc_format": True, "strict_citation_verify": False, "purpose": "毕业论文"}
    app_v2.store.put(session)

    client = _client()
    resp = client.get(f"/api/doc/{session.id}/export/check?format=docx&auto_fix=0")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("can_export") is False
    codes = {str(item.get("code") or "") for item in (body.get("issues") or []) if isinstance(item, dict)}
    assert "figure_mention_without_object" in codes
    assert "table_mention_without_object" in codes


def test_export_check_blocks_insufficient_h2_h3_depth_for_academic_doc() -> None:
    session = app_v2.store.create()
    text = "\n".join(
        [
            "# Thesis Title",
            "",
            "## Abstract",
            "",
            ("This is abstract text. " * 40).strip(),
            "",
            "## Keywords",
            "",
            "writing agent; docir; export",
            "",
            "## 1 Introduction",
            "",
            ("intro content " * 180).strip(),
            "",
            "## 2 Method",
            "",
            ("method content " * 180).strip(),
            "",
            "## References",
            "",
            "[1] Author A. Paper One[J]. Journal A, 2024.",
            "[2] Author B. Paper Two[J]. Journal B, 2024.",
            "[3] Author C. Paper Three[J]. Journal C, 2024.",
            "[4] Author D. Paper Four[J]. Journal D, 2024.",
            "[5] Author E. Paper Five[J]. Journal E, 2024.",
            "[6] Author F. Paper Six[J]. Journal F, 2024.",
            "[7] Author G. Paper Seven[J]. Journal G, 2024.",
            "[8] Author H. Paper Eight[J]. Journal H, 2024.",
        ]
    )
    app_v2._set_doc_text(session, text)
    session.generation_prefs = {
        "strict_doc_format": True,
        "strict_citation_verify": False,
        "purpose": "undergraduate thesis",
        "min_reference_count": 8,
        "min_h2_count": 3,
        "min_h3_count": 1,
    }
    app_v2.store.put(session)

    client = _client()
    resp = client.get(f"/api/doc/{session.id}/export/check?format=docx&auto_fix=0")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("can_export") is False
    codes = {str(item.get("code") or "") for item in (body.get("issues") or []) if isinstance(item, dict)}
    assert "heading_depth_h2_insufficient" in codes
    assert "heading_depth_h3_insufficient" in codes


def test_export_check_blocks_non_gbt7714_reference_items_for_academic_doc() -> None:
    session = app_v2.store.create()
    text = "\n".join(
        [
            "# Thesis Title",
            "",
            "## Abstract",
            "",
            ("This is abstract text. " * 40).strip(),
            "",
            "## Keywords",
            "",
            "writing agent; docir; export",
            "",
            "## 1 Introduction",
            "",
            ("intro content " * 180).strip(),
            "",
            "### 1.1 Background",
            "",
            ("background content " * 80).strip(),
            "",
            "## 2 Method",
            "",
            ("method content " * 180).strip(),
            "",
            "### 2.1 Pipeline",
            "",
            ("pipeline content " * 80).strip(),
            "",
            "## References",
            "",
            "[1] OpenAI Structured Outputs https://platform.openai.com/docs/guides/structured-output",
            "[2] Anthropic XML tags https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/use-xml-tags",
            "[3] RFC 5789 https://www.rfc-editor.org/rfc/rfc5789",
            "[4] RFC 6902 https://www.rfc-editor.org/rfc/rfc6902",
            "[5] LaserTagger https://aclanthology.org/D19-1510",
            "[6] Levenshtein Transformer https://arxiv.org/abs/1905.11006",
            "[7] EditEval benchmark https://arxiv.org/abs/2501.12345",
            "[8] Self-Refine https://arxiv.org/abs/2303.17651",
        ]
    )
    app_v2._set_doc_text(session, text)
    session.generation_prefs = {
        "strict_doc_format": True,
        "strict_citation_verify": False,
        "purpose": "undergraduate thesis",
        "min_reference_count": 8,
        "min_h2_count": 2,
        "min_h3_count": 1,
    }
    app_v2.store.put(session)

    client = _client()
    resp = client.get(f"/api/doc/{session.id}/export/check?format=docx&auto_fix=0")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("can_export") is False
    issues = [item for item in (body.get("issues") or []) if isinstance(item, dict)]
    codes = {str(item.get("code") or "") for item in issues}
    assert "reference_gbt7714_noncompliant" in codes
    gbt_issue = next((x for x in issues if str(x.get("code") or "") == "reference_gbt7714_noncompliant"), {})
    meta = gbt_issue.get("meta") if isinstance(gbt_issue, dict) else {}
    assert isinstance(meta, dict)
    assert int(meta.get("violation_count") or 0) >= 1


def test_export_check_blocks_reference_numbering_gaps() -> None:
    session = app_v2.store.create()
    text = "\n".join(
        [
            "# Thesis Title",
            "",
            "## Abstract",
            "",
            ("This is abstract text. " * 40).strip(),
            "",
            "## Keywords",
            "",
            "writing agent; docir; export",
            "",
            "## 1 Introduction",
            "",
            ("intro content " * 180).strip(),
            "",
            "### 1.1 Background",
            "",
            ("background content " * 80).strip(),
            "",
            "## 2 Method",
            "",
            ("method content " * 180).strip(),
            "",
            "### 2.1 Pipeline",
            "",
            ("pipeline content " * 80).strip(),
            "",
            "## References",
            "",
            "[1] Author A. Paper One[J]. Journal A, 2024.",
            "[3] Author B. Paper Two[J]. Journal B, 2024.",
            "[4] Author C. Paper Three[J]. Journal C, 2024.",
            "[5] Author D. Paper Four[J]. Journal D, 2024.",
            "[6] Author E. Paper Five[J]. Journal E, 2024.",
            "[7] Author F. Paper Six[J]. Journal F, 2024.",
            "[8] Author G. Paper Seven[J]. Journal G, 2024.",
            "[9] Author H. Paper Eight[J]. Journal H, 2024.",
        ]
    )
    app_v2._set_doc_text(session, text)
    session.generation_prefs = {
        "strict_doc_format": True,
        "strict_citation_verify": False,
        "purpose": "undergraduate thesis",
        "min_reference_count": 8,
        "min_h2_count": 2,
        "min_h3_count": 1,
    }
    app_v2.store.put(session)

    client = _client()
    resp = client.get(f"/api/doc/{session.id}/export/check?format=docx&auto_fix=0")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("can_export") is False
    codes = {str(item.get("code") or "") for item in (body.get("issues") or []) if isinstance(item, dict)}
    assert "reference_numbering_invalid" in codes


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
