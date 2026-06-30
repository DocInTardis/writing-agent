# RAG Trust Guard

Enhanced retrieval stack:

- `writing_agent/v2/rag/retrieve.py`
- `writing_agent/v2/rag/preprocess.py`
- `writing_agent/v2/rag/sectioning.py`
- `writing_agent/v2/rag/structured_store.py`
- `writing_agent/v2/rag/hierarchical_retriever.py`
- `writing_agent/v2/rag/citation_registry.py`
- `writing_agent/v2/rag/query_expand.py`
- `writing_agent/v2/rag/re_rank.py`
- `writing_agent/v2/rag/source_quality.py`
- `writing_agent/v2/rag/citation_integrity.py`
- `writing_agent/v2/rag/knowledge_snapshot.py`

Features:

- hybrid retrieval with multi-query expansion
- idempotent source, section, evidence, and citation records
- page-aware PDF extraction with structure-first section parsing
- section-first recall followed by evidence-only ranking
- optional section/evidence embeddings with keyword fallback
- legacy chunk fallback during migration
- background metadata discovery and indexing outside generation latency
- generated-claim to evidence registration
- references derived from registered citations when supported matches exist
- rerank stage
- source quality scoring + near-duplicate labeling
- citation reachability and metadata consistency helpers
- citation span grounding helper
- no-evidence downgrade message
- versioned knowledge snapshots for reproducible offline evaluation

## Migration

Rebuild structured records from the existing paper store:

```powershell
.\.venv\Scripts\python.exe scripts\rag_rebuild_structured.py --rag-dir .data\rag
```

Use `--no-embed` when the embedding service is unavailable. Add `--force` after
changing parser or compression behavior.

The migration is additive. Existing `chunks.jsonl` remains available as a
fallback until structured retrieval has been evaluated against a labeled query
set.

## Runtime switches

- `WRITING_AGENT_RAG_HIERARCHICAL_ENABLED=1`
- `WRITING_AGENT_RAG_ONLINE_FILL_ENABLED=0`
- `WRITING_AGENT_RAG_AUTO_FETCH_ENABLED=1`
- `WRITING_AGENT_RAG_EXPAND_ENABLED=1`
- `WRITING_AGENT_RAG_AUDIT_ENABLED=1`
- `WRITING_AGENT_RAG_RETRY_FAILED_ENABLED=1`

Online fill is disabled by default. Discovery and related-paper expansion are
scheduled as daemon background work and only `ready` structured sources
participate in hierarchical retrieval.

## Evaluation

`writing_agent.v2.rag.evaluation.evaluate_cases` reports:

- section Recall@K
- evidence Precision@K
- MRR
- nDCG@K

Retrieval trails are written under `<rag_dir>/audit/retrieval_trails.jsonl` for
offline review.
