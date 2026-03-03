import json
from types import SimpleNamespace

from writing_agent.web.domains import revision_edit_runtime_domain as red


def _settings():
    return SimpleNamespace(enabled=True, base_url="http://127.0.0.1:11434", model="qwen2.5:1.5b", timeout_s=5.0)


class _FakeStructuredClient:
    def __init__(self, *, base_url: str, model: str, timeout_s: float) -> None:
        self.base_url = base_url
        self.model = model
        self.timeout_s = timeout_s

    def is_running(self) -> bool:
        return True

    def chat(self, *, system: str, user: str, temperature: float = 0.2) -> str:
        _ = system, user, temperature
        return (
            '{"ops":[{"op":"replace","value":"Improved sentence."}],'
            '"meta":{"risk_level":"low","notes":"ok"},'
            '"checks":{"preserve_markers":true}}'
        )


class _FakeAlwaysInvalidClient:
    def __init__(self, *, base_url: str, model: str, timeout_s: float) -> None:
        self.base_url = base_url
        self.model = model
        self.timeout_s = timeout_s

    def is_running(self) -> bool:
        return True

    def chat(self, *, system: str, user: str, temperature: float = 0.2) -> str:
        _ = system, user, temperature
        return "not-json"


class _FakeRefineRecoverClient:
    calls = 0

    def __init__(self, *, base_url: str, model: str, timeout_s: float) -> None:
        self.base_url = base_url
        self.model = model
        self.timeout_s = timeout_s

    def is_running(self) -> bool:
        return True

    def chat(self, *, system: str, user: str, temperature: float = 0.2) -> str:
        _ = system, user, temperature
        _FakeRefineRecoverClient.calls += 1
        if _FakeRefineRecoverClient.calls == 1:
            return "not-json"
        return (
            '{"ops":[{"op":"replace","value":"Refined sentence."}],'
            '"meta":{"risk_level":"low","notes":"refined"},'
            '"checks":{"preserve_markers":true}}'
        )


def _read_jsonl(path):
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def test_selected_revision_metrics_record_success(monkeypatch, tmp_path):
    metrics_path = tmp_path / "selected_revision_events.jsonl"
    monkeypatch.setenv("WRITING_AGENT_SELECTED_REVISION_METRICS_ENABLE", "1")
    monkeypatch.setenv("WRITING_AGENT_SELECTED_REVISION_METRICS_PATH", str(metrics_path))

    base = "Before context. Old sentence. After context."
    start = base.index("Old")
    end = start + len("Old")

    out = red.try_revision_edit(
        session=None,
        instruction="make it clearer",
        text=base,
        selection={"start": start, "end": end, "text": "Old"},
        analysis=None,
        context_policy={"version": "dynamic_v1"},
        sanitize_output_text=lambda x: str(x or "").strip(),
        replace_question_headings=lambda x: x,
        get_ollama_settings_fn=_settings,
        ollama_client_cls=_FakeStructuredClient,
    )
    assert out is not None

    rows = _read_jsonl(metrics_path)
    events = [str(r.get("event") or "") for r in rows]
    assert "package_ready" in events
    assert "apply_success" in events
    success_rows = [r for r in rows if str(r.get("event") or "") == "apply_success"]
    assert success_rows
    assert str(success_rows[-1].get("policy_version") or "") == "dynamic_v1"


def test_selected_revision_metrics_record_refine_failed(monkeypatch, tmp_path):
    metrics_path = tmp_path / "selected_revision_events.jsonl"
    monkeypatch.setenv("WRITING_AGENT_SELECTED_REVISION_METRICS_ENABLE", "1")
    monkeypatch.setenv("WRITING_AGENT_SELECTED_REVISION_METRICS_PATH", str(metrics_path))
    monkeypatch.setenv("WRITING_AGENT_REVISE_ALLOW_PLAIN_TEXT", "0")

    base = "Before context. Old sentence. After context."
    start = base.index("Old sentence.")
    end = start + len("Old sentence.")

    out = red.try_revision_edit(
        session=None,
        instruction="rewrite selected sentence",
        text=base,
        selection={"start": start, "end": end, "text": "Old sentence."},
        analysis=None,
        context_policy={"version": "dynamic_v1"},
        sanitize_output_text=lambda x: str(x or "").strip(),
        replace_question_headings=lambda x: x,
        get_ollama_settings_fn=_settings,
        ollama_client_cls=_FakeAlwaysInvalidClient,
    )
    assert out is None

    rows = _read_jsonl(metrics_path)
    assert any(str(r.get("event") or "") == "fallback_triggered" for r in rows)
    assert any(
        str(r.get("event") or "") == "fallback_failed"
        and str(r.get("error_code") or "") == "E_REFINE_FAILED"
        for r in rows
    )


def test_selected_revision_metrics_refine_failure_can_be_injected(monkeypatch, tmp_path):
    metrics_path = tmp_path / "selected_revision_events_injected.jsonl"
    monkeypatch.setenv("WRITING_AGENT_SELECTED_REVISION_METRICS_ENABLE", "1")
    monkeypatch.setenv("WRITING_AGENT_SELECTED_REVISION_METRICS_PATH", str(metrics_path))
    monkeypatch.setenv("WRITING_AGENT_REVISE_ALLOW_PLAIN_TEXT", "0")
    monkeypatch.setenv("WRITING_AGENT_FAIL_INJECT_SELECTED_REVISION_REFINE", "1")

    _FakeRefineRecoverClient.calls = 0
    base = "Before context. Old sentence. After context."
    start = base.index("Old sentence.")
    end = start + len("Old sentence.")

    out = red.try_revision_edit(
        session=None,
        instruction="rewrite selected sentence",
        text=base,
        selection={"start": start, "end": end, "text": "Old sentence."},
        analysis=None,
        context_policy={"version": "dynamic_v1"},
        sanitize_output_text=lambda x: str(x or "").strip(),
        replace_question_headings=lambda x: x,
        get_ollama_settings_fn=_settings,
        ollama_client_cls=_FakeRefineRecoverClient,
    )
    assert out is None
    assert _FakeRefineRecoverClient.calls == 2

    rows = _read_jsonl(metrics_path)
    assert any(str(r.get("event") or "") == "fallback_triggered" for r in rows)
    assert any(
        str(r.get("event") or "") == "fallback_failed"
        and str(r.get("error_code") or "") == "E_REFINE_FAILED"
        for r in rows
    )
