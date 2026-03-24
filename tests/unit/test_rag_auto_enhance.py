from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

from writing_agent.v2.rag import auto_enhance as auto_enhance_module


class _FakeWork:
    def __init__(self, paper_id: str, title: str | None = None):
        self.paper_id = paper_id
        self.title = title or paper_id


class _FakeStore:
    _papers_by_dir: dict[str, list[_FakeWork]] = {}
    _lock = threading.Lock()

    def __init__(self, rag_dir):
        self._key = str(rag_dir)
        with self._lock:
            self._papers_by_dir.setdefault(self._key, [])

    def list_papers(self):
        with self._lock:
            return list(self._papers_by_dir[self._key])

    def put_openalex_work(self, work, pdf_bytes=None):
        _ = pdf_bytes
        with self._lock:
            papers = self._papers_by_dir[self._key]
            if any(getattr(x, 'paper_id', '') == getattr(work, 'paper_id', '') for x in papers):
                return
            papers.append(work)



def test_auto_fetch_on_empty_is_deduplicated_per_rag_dir(monkeypatch, tmp_path):
    rag_dir = tmp_path / 'rag'
    rag_dir.mkdir(parents=True, exist_ok=True)
    calls: list[str] = []

    def _fake_search_openalex(*, query: str, max_results: int = 5):
        _ = max_results
        calls.append(query)
        time.sleep(0.05)
        return SimpleNamespace(works=[_FakeWork(f'id-{i}') for i in range(5)])

    monkeypatch.setattr('writing_agent.v2.rag.store.RagStore', _FakeStore)
    monkeypatch.setattr('writing_agent.v2.rag.openalex.search_openalex', _fake_search_openalex)

    with ThreadPoolExecutor(max_workers=4) as ex:
        results = list(
            ex.map(
                lambda _n: auto_enhance_module.auto_fetch_on_empty(
                    rag_dir=rag_dir,
                    query='blockchain rural service',
                    min_papers=5,
                ),
                range(4),
            )
        )

    assert calls == ['blockchain']
    assert results.count(True) == 1
    assert results.count(False) == 3



def test_expand_with_related_respects_cooldown(monkeypatch, tmp_path):
    rag_dir = tmp_path / 'rag_expand'
    rag_dir.mkdir(parents=True, exist_ok=True)
    _FakeStore._papers_by_dir[str(rag_dir)] = [_FakeWork('seed-1', title='blockchain rural service')]
    calls: list[str] = []

    def _fake_search_openalex(*, query: str, max_results: int = 3):
        _ = max_results
        calls.append(query)
        return SimpleNamespace(works=[_FakeWork('extra-1', title='extra paper')])

    monkeypatch.setattr('writing_agent.v2.rag.store.RagStore', _FakeStore)
    monkeypatch.setattr('writing_agent.v2.rag.openalex.search_openalex', _fake_search_openalex)
    monkeypatch.setenv('WRITING_AGENT_RAG_EXPAND_COOLDOWN_S', '3600')
    auto_enhance_module._RELATED_EXPAND_STATE.clear()

    added_first = auto_enhance_module.expand_with_related(
        rag_dir=rag_dir,
        paper_ids=['seed-1'],
        max_expand=3,
    )
    added_second = auto_enhance_module.expand_with_related(
        rag_dir=rag_dir,
        paper_ids=['seed-1'],
        max_expand=3,
    )

    assert added_first == 1
    assert added_second == 0
    assert len(calls) == 1
    assert set(calls[0].split()) == {'blockchain', 'rural', 'service'}



def test_auto_fetch_on_empty_respects_cooldown_after_failed_attempt(monkeypatch, tmp_path):
    rag_dir = tmp_path / 'rag_cooldown'
    rag_dir.mkdir(parents=True, exist_ok=True)
    _FakeStore._papers_by_dir[str(rag_dir)] = []
    calls: list[str] = []

    def _fake_search_openalex(*, query: str, max_results: int = 5):
        _ = max_results
        calls.append(query)
        raise RuntimeError('429')

    monkeypatch.setattr('writing_agent.v2.rag.store.RagStore', _FakeStore)
    monkeypatch.setattr('writing_agent.v2.rag.openalex.search_openalex', _fake_search_openalex)
    monkeypatch.setenv('WRITING_AGENT_RAG_AUTO_FETCH_COOLDOWN_S', '3600')
    auto_enhance_module._AUTO_FETCH_STATE.clear()

    result1 = auto_enhance_module.auto_fetch_on_empty(
        rag_dir=rag_dir,
        query='blockchain rural service',
        min_papers=5,
    )
    result2 = auto_enhance_module.auto_fetch_on_empty(
        rag_dir=rag_dir,
        query='blockchain rural service',
        min_papers=5,
    )

    assert result1 is False
    assert result2 is False
    assert len(calls) == 1



def test_auto_fetch_on_empty_can_be_disabled_by_env(monkeypatch, tmp_path):
    rag_dir = tmp_path / 'rag_disabled'
    rag_dir.mkdir(parents=True, exist_ok=True)
    calls: list[str] = []

    def _fake_search_openalex(*, query: str, max_results: int = 5):
        _ = max_results
        calls.append(query)
        return SimpleNamespace(works=[_FakeWork('x')])

    monkeypatch.setattr('writing_agent.v2.rag.store.RagStore', _FakeStore)
    monkeypatch.setattr('writing_agent.v2.rag.openalex.search_openalex', _fake_search_openalex)
    monkeypatch.setenv('WRITING_AGENT_RAG_AUTO_FETCH_ENABLED', '0')

    result = auto_enhance_module.auto_fetch_on_empty(
        rag_dir=rag_dir,
        query='blockchain rural service',
        min_papers=5,
    )

    assert result is False
    assert calls == []


def test_expand_with_related_can_be_disabled_by_env(monkeypatch, tmp_path):
    rag_dir = tmp_path / 'rag_expand_disabled'
    rag_dir.mkdir(parents=True, exist_ok=True)
    _FakeStore._papers_by_dir[str(rag_dir)] = [_FakeWork('seed-1', title='blockchain rural service')]
    calls: list[str] = []

    def _fake_search_openalex(*, query: str, max_results: int = 3):
        _ = max_results
        calls.append(query)
        return SimpleNamespace(works=[_FakeWork('extra-1', title='extra paper')])

    monkeypatch.setattr('writing_agent.v2.rag.store.RagStore', _FakeStore)
    monkeypatch.setattr('writing_agent.v2.rag.openalex.search_openalex', _fake_search_openalex)
    monkeypatch.setenv('WRITING_AGENT_RAG_EXPAND_ENABLED', '0')

    added = auto_enhance_module.expand_with_related(
        rag_dir=rag_dir,
        paper_ids=['seed-1'],
        max_expand=3,
    )

    assert added == 0
    assert calls == []
