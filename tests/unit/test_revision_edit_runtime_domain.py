from __future__ import annotations

from types import SimpleNamespace

from writing_agent.web.domains import revision_edit_runtime_domain as domain


class _FakeClient:
    def __init__(self, *args, **kwargs):
        _ = args, kwargs
        self._responses: list[str] = []

    def is_running(self) -> bool:
        return True

    def chat_stream(self, system: str, user: str, temperature: float):
        _ = system, user, temperature
        if self._responses:
            payload = self._responses.pop(0)
        else:
            payload = "<revised_document>\n# 标题\n\n## 引言\n改写后内容。\n</revised_document>"
        yield payload


def _settings():
    return SimpleNamespace(enabled=True, model="demo", base_url="http://test", timeout_s=5.0)


def test_full_document_revision_single_path_success() -> None:
    statuses: list[dict] = []

    out = domain.try_revision_edit(
        session=None,
        instruction="请润色全文",
        text="# 标题\n\n## 引言\n原始内容。",
        selection="",
        analysis=None,
        context_policy=None,
        report_status=lambda payload: statuses.append(dict(payload)),
        sanitize_output_text=lambda s: str(s or "").strip(),
        replace_question_headings=lambda s: s,
        get_ollama_settings_fn=_settings,
        ollama_client_cls=_FakeClient,
    )

    assert out is not None
    assert out[1] == "revision applied (full_document)"
    assert "改写后内容" in out[0]
    assert statuses
    assert statuses[-1].get("ok") is True
    assert statuses[-1].get("selection_source") == "full_document"


def test_full_document_revision_retries_when_missing_wrapper() -> None:
    statuses: list[dict] = []

    class _RetryClient(_FakeClient):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._responses = [
                "这里没有标签包裹",
                "<revised_document>\n# 标题\n\n## 引言\n二次重试成功。\n</revised_document>",
            ]

    out = domain.try_revision_edit(
        session=None,
        instruction="请改写全文",
        text="# 标题\n\n## 引言\n原文。",
        selection="",
        analysis=None,
        context_policy=None,
        report_status=lambda payload: statuses.append(dict(payload)),
        sanitize_output_text=lambda s: str(s or "").strip(),
        replace_question_headings=lambda s: s,
        get_ollama_settings_fn=_settings,
        ollama_client_cls=_RetryClient,
    )

    assert out is not None
    assert "二次重试成功" in out[0]
    assert statuses[-1].get("ok") is True
