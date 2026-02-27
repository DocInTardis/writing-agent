# RAG Trust Guard

Enhanced retrieval stack:

- `writing_agent/v2/rag/retrieve.py`
- `writing_agent/v2/rag/query_expand.py`
- `writing_agent/v2/rag/re_rank.py`
- `writing_agent/v2/rag/source_quality.py`
- `writing_agent/v2/rag/citation_integrity.py`
- `writing_agent/v2/rag/knowledge_snapshot.py`

Features:

- hybrid retrieval with multi-query expansion
- rerank stage
- source quality scoring + near-duplicate labeling
- citation reachability and metadata consistency helpers
- citation span grounding helper
- no-evidence downgrade message
- versioned knowledge snapshots for reproducible offline evaluation
