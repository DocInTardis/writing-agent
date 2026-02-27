from pathlib import Path

from writing_agent.v2.rag.knowledge_snapshot import latest_snapshot, save_snapshot


def test_knowledge_snapshot_roundtrip(tmp_path) -> None:
    path = save_snapshot(rag_dir=tmp_path, name='baseline', payload={'x': 1})
    assert path.exists()
    latest = latest_snapshot(rag_dir=tmp_path, name='baseline')
    assert latest is not None and latest.exists()
