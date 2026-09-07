from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_stream_checks_cancellation_before_every_document_write() -> None:
    source = (ROOT / "writing_agent/web/legacy_fragments/generation_stream.py").read_text(encoding="utf-8")
    iterator = source[source.index("    def _iter():") : source.index("    return StreamingResponse", source.index("    def _iter():"))]
    chunks = iterator.split("app_v2._set_doc_text(session,")
    assert len(chunks) == 4
    for prefix in chunks[:-1]:
        assert "if _cancelled():" in prefix[-260:]
    assert "stream.close()" in iterator


def test_frontend_stop_notifies_server_and_does_not_auto_fallback() -> None:
    source = (ROOT / "writing_agent/web/frontend_svelte/src/AppWorkbench.svelte").read_text(encoding="utf-8")
    stop = source[source.index("  function handleStop()") : source.index("  function runEditorCommand", source.index("  function handleStop()"))]
    assert "/generate/cancel" in stop
    assert "userCancelled = true" in stop
    assert "切换非流式生成" not in source
    assert "!sawFinal && !userCancelled" in source
