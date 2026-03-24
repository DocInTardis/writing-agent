from __future__ import annotations

from types import SimpleNamespace

from writing_agent.v2.rag import retrieve as retrieve_module


class _FakeIndex:
    def __init__(self, rag_dir):
        self.index_path = type("P", (), {"exists": lambda self: False})()


class _FakeStore:
    def __init__(self, rag_dir):
        self.rag_dir = rag_dir

    def list_papers(self):
        return []


def test_retrieve_context_skips_online_fill_when_disabled(monkeypatch, tmp_path):
    rag_dir = tmp_path / "rag"
    rag_dir.mkdir(parents=True, exist_ok=True)
    calls = {"online": 0}

    def _fake_search_openalex(**kwargs):
        calls["online"] += 1
        return SimpleNamespace(works=[])

    monkeypatch.setenv("WRITING_AGENT_RAG_ONLINE_FILL_ENABLED", "0")
    monkeypatch.setenv("WRITING_AGENT_RAG_AUTO_FETCH_ENABLED", "0")
    monkeypatch.setenv("WRITING_AGENT_RAG_EXPAND_ENABLED", "0")
    monkeypatch.setattr(retrieve_module, "RagIndex", _FakeIndex)
    monkeypatch.setattr(retrieve_module, "RagStore", _FakeStore)
    monkeypatch.setattr(retrieve_module, "expand_queries", lambda q, max_queries=4: [q])
    monkeypatch.setattr(retrieve_module, "search_openalex", _fake_search_openalex)
    monkeypatch.setattr(retrieve_module, "search_papers", lambda papers, query, top_k: [])
    monkeypatch.setattr(retrieve_module, "build_rag_context", lambda hits, max_chars: "")

    result = retrieve_module.retrieve_context(
        rag_dir=rag_dir,
        query="blockchain rural service",
        top_k=3,
        per_paper=1,
        max_chars=800,
    )

    assert result.online_hits == 0
    assert calls["online"] == 0


def test_online_topup_sets_cooldown_after_429(monkeypatch):
    retrieve_module._ONLINE_TOPUP_DISABLED_UNTIL = 0.0
    monkeypatch.setenv("WRITING_AGENT_RAG_ONLINE_FILL_ENABLED", "1")
    monkeypatch.setenv("WRITING_AGENT_RAG_ONLINE_429_COOLDOWN_S", "600")

    calls = {"online": 0}

    def _fake_search_openalex(**kwargs):
        calls["online"] += 1
        raise RuntimeError("HTTP Error 429: Too Many Requests")

    monkeypatch.setattr(retrieve_module, "search_openalex", _fake_search_openalex)

    rows1 = retrieve_module._online_topup_hits(query="blockchain rural service", existing_hits=[], top_k=3, per_paper=1)
    rows2 = retrieve_module._online_topup_hits(query="blockchain rural service", existing_hits=[], top_k=3, per_paper=1)

    assert rows1 == []
    assert rows2 == []
    assert calls["online"] == 1
