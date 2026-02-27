from writing_agent.v2.rag.query_expand import expand_queries
from writing_agent.v2.rag.re_rank import RerankItem, rerank_texts
from writing_agent.v2.rag.source_quality import score_source
from writing_agent.v2.rag.citation_integrity import citation_span_grounding, check_metadata_consistency


def test_expand_queries_returns_multi() -> None:
    rows = expand_queries('cache optimization, latency, throughput', max_queries=4)
    assert len(rows) >= 2


def test_rerank_texts() -> None:
    items = [RerankItem(text='alpha', score=0.2), RerankItem(text='query alpha beta', score=0.1)]
    out = rerank_texts(query='query', items=items, top_k=2)
    assert out[0].text == 'query alpha beta'


def test_source_quality_levels() -> None:
    high = score_source(url='https://arxiv.org/abs/1234.5678', author='foo')
    low = score_source(url='https://example.com/x')
    assert high.score > low.score


def test_citation_grounding_and_metadata() -> None:
    spans = citation_span_grounding('text [1] more [2]', [{'id': '1', 'marker': '[1]'}, {'id': '2', 'marker': '[2]'}])
    assert len(spans) == 2
    assert check_metadata_consistency(title='A Study', source_title='A Study on X', author='Tom', source_author='Tom Lee')
