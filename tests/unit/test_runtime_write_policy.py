from __future__ import annotations

import json
import queue
from collections import deque
from pathlib import Path
from types import SimpleNamespace

import pytest

from writing_agent.state_engine.checkpoint_store import CheckpointStore
from writing_agent.v2 import graph_runner_policy_domain as metrics
from writing_agent.v2 import graph_runner_runtime_session_domain as runtime
from writing_agent.v2 import graph_section_draft_domain as blocks
from writing_agent.v2.text_store import TextStore


@pytest.fixture
def metric_path(tmp_path, monkeypatch):
    path = tmp_path / "metrics" / "phase.json"
    monkeypatch.setattr(metrics, "_PHASE_METRICS_PATH", path)
    monkeypatch.setattr(metrics, "_PHASE_METRICS_PENDING", deque(maxlen=200))
    monkeypatch.delenv("WRITING_AGENT_PERSIST_PHASE_METRICS", raising=False)
    return path


def test_normal_generation_diagnostics_do_not_write_files(metric_path):
    for i in range(100):
        metrics._record_phase_timing("run", {"phase": "PLAN", "event": "step", "i": i})
    metrics._record_phase_timing("run", {"phase": "TOTAL", "event": "end"})
    assert not metric_path.parent.exists()
    assert not metrics._PHASE_METRICS_PENDING


def test_debug_metrics_batch_once_and_isolate_runs(metric_path, monkeypatch):
    monkeypatch.setenv("WRITING_AGENT_PERSIST_PHASE_METRICS", "1")
    writes = []
    save = metrics._save_phase_metrics

    def counted(data):
        writes.append(data)
        save(data)

    monkeypatch.setattr(metrics, "_save_phase_metrics", counted)
    for i in range(50):
        metrics._record_phase_timing("a", {"phase": "PLAN", "i": i})
    metrics._record_phase_timing("b", {"phase": "PLAN"})
    assert not metric_path.exists()
    metrics._record_phase_timing("a", {"phase": "TOTAL", "event": "end"})
    metrics._flush_phase_timing("a")
    assert len(writes) == 1
    assert len(json.loads(metric_path.read_text())["runs"]) == 51
    assert len(metrics._PHASE_METRICS_PENDING) == 1
    metrics._flush_phase_timing("b")
    assert len(writes) == 2
    assert not metrics._PHASE_METRICS_PENDING
    assert not metric_path.with_suffix(".json.tmp").exists()


@pytest.mark.parametrize("failure", [False, True])
def test_metrics_flush_on_generator_close_or_failure(metric_path, monkeypatch, failure):
    monkeypatch.setenv("WRITING_AGENT_PERSIST_PHASE_METRICS", "1")

    def fake(_api, *, run_id, **kwargs):
        metrics._record_phase_timing(run_id, {"phase": "PLAN"})
        if failure:
            raise RuntimeError("failed task")
        yield {"event": "progress"}

    monkeypatch.setattr(runtime, "_run_generate_graph_impl", fake)
    stream = runtime.run_generate_graph_impl(None, instruction="", current_text="", required_h2=[], config=None)
    if failure:
        with pytest.raises(RuntimeError, match="failed task"):
            list(stream)
    else:
        next(stream)
        assert not metric_path.exists()
        stream.close()
    assert len(json.loads(metric_path.read_text())["runs"]) == 1
    assert not metrics._PHASE_METRICS_PENDING


def test_optional_metric_write_failure_does_not_fail_task(metric_path, monkeypatch):
    monkeypatch.setenv("WRITING_AGENT_PERSIST_PHASE_METRICS", "1")

    def fail(_data):
        raise OSError("disk unavailable")

    monkeypatch.setattr(metrics, "_save_phase_metrics", fail)
    metrics._record_phase_timing("run", {"phase": "TOTAL", "event": "end"})
    assert not metrics._PHASE_METRICS_PENDING


def test_text_store_is_lazy_and_deduplicates_across_instances(tmp_path):
    root = tmp_path / "blocks"
    store = TextStore(root)
    assert not root.exists()
    bid = store.put_text("相同正文")
    path = root / f"{bid}.txt"
    before = path.stat().st_mtime_ns
    for _ in range(100):
        assert TextStore(root).put_text("相同正文") == bid
    assert path.stat().st_mtime_ns == before
    assert list(root.iterdir()) == [path]
    assert store.get_text(bid) == "相同正文"


def test_json_blocks_are_compact_and_canonical(tmp_path):
    store = TextStore(tmp_path)
    bid = store.put_json({"b": [1, 2], "a": "中"}, prefix="t")
    assert store.put_json({"a": "中", "b": [1, 2]}, prefix="t") == bid
    assert store.get_json(bid) == {"a": "中", "b": [1, 2]}
    assert (tmp_path / f"{bid}.json").read_text(encoding="utf-8") == '{"a":"中","b":[1,2]}'


def test_content_addressed_blocks_cannot_mutate_shared_old_content(tmp_path):
    store = TextStore(tmp_path)
    old = store.put_text("old")
    new = store.put_text("new", block_id=old)
    assert new != old
    assert store.get_text(old) == "old"
    assert store.get_text(new) == "new"
    assert store.put_text("legacy", block_id="p_12345678") == "p_12345678"
    assert store.put_text("updated", block_id="p_12345678") == "p_12345678"
    assert store.get_text("p_12345678") == "updated"


def test_text_store_rejects_traversal_and_preserves_existing_on_write_failure(tmp_path, monkeypatch):
    store = TextStore(tmp_path)
    with pytest.raises(ValueError, match="invalid block id"):
        store.put_text("bad", block_id="../document")
    store.put_text("old", block_id="legacy")

    def fail(*_args):
        raise OSError("replace failed")

    monkeypatch.setattr("writing_agent.v2.text_store.os.replace", fail)
    with pytest.raises(OSError):
        store.put_text("new", block_id="legacy")
    assert store.get_text("legacy") == "old"
    assert not list(tmp_path.glob("*.tmp"))


def test_checkpoints_use_data_root_skip_duplicates_and_keep_replay(tmp_path, monkeypatch):
    monkeypatch.setenv("WRITING_AGENT_DATA_DIR", str(tmp_path))
    store = CheckpointStore()
    assert not store.root.exists()
    state = {"draft": "hello", "schema_version": "1"}
    events = [{"node_id": "writer", "patch": {"draft": "hello"}}]
    path = store.save("task", state, events)
    before = path.stat().st_mtime_ns
    assert store.save("task", state, events) == path
    assert path.stat().st_mtime_ns == before
    assert store.load("task")["events"] == events
    assert "\n" not in path.read_text()
    assert path.parent == tmp_path / "graph_checkpoints"
    store.append_event("task", {"status": "interrupted"})
    assert len(store.load("task")["events"]) == 2


def test_checkpoint_atomic_failure_preserves_prior_resume_state(tmp_path, monkeypatch):
    store = CheckpointStore(tmp_path)
    store.save("task", {"draft": "old"}, [])

    def fail(*_args):
        raise OSError("replace failed")

    monkeypatch.setattr("writing_agent.state_engine.checkpoint_store.os.replace", fail)
    with pytest.raises(OSError):
        store.save("task", {"draft": "new"}, [])
    assert store.load("task")["state"] == {"draft": "old"}
    assert not list(tmp_path.glob("*.tmp"))


def test_supported_launchers_disable_bytecode():
    root = Path(__file__).resolve().parents[2]
    for filename, module in [("start.ps1", "launch"), ("start_desktop.ps1", "desktop_app")]:
        script = (root / "scripts" / filename).read_text(encoding="utf-8")
        assert f"& $python -B -m writing_agent.{module}" in script
        assert '$env:PYTHONDONTWRITEBYTECODE = "1"' in script


def test_normal_generation_does_not_construct_disk_block_store(tmp_path, monkeypatch):
    monkeypatch.delenv("WRITING_AGENT_PERSIST_TEXT_BLOCKS", raising=False)

    def forbidden(*_args):
        raise AssertionError("normal generation must not create a disk block store")

    assert runtime._create_text_store(SimpleNamespace(TextStore=forbidden), tmp_path) is None
    monkeypatch.setenv("WRITING_AGENT_PERSIST_TEXT_BLOCKS", "1")
    store = runtime._create_text_store(SimpleNamespace(TextStore=TextStore), tmp_path)
    assert store.root == tmp_path / "text_store"
    assert not store.root.exists()


@pytest.mark.parametrize("block", [
    {"type": "paragraph", "text": "正文"},
    {"type": "list", "items": ["第一项", "第二项"]},
    {"type": "table", "caption": "表", "columns": ["A"], "rows": [[1]]},
    {"type": "figure", "caption": "图", "kind": "bar", "data": {"values": [1]}},
])
def test_inline_blocks_emit_complete_content_without_phantom_file_ids(block, monkeypatch):
    monkeypatch.setattr(blocks, "_hits_semantic_sampling_guard", lambda *_: [])
    out = queue.Queue()
    block = dict(block, section_id="s", block_id="model-id")
    texts = []
    blocks._process_block(
        block, section="Section", section_id="s", is_reference=False, text_store=None,
        seen=set(), seen_norm=set(), texts=texts, plain_lines=[], out_queue=out,
        emitted_chars=0, last_norm="", repeat_streak=0, stop_threshold=0,
    )
    event = out.get_nowait()
    assert event["delta"] == blocks.render_block_to_text(block)
    assert texts == [event["delta"]]
    assert "block_id" not in event


def test_legacy_table_block_still_has_readable_file_id(tmp_path, monkeypatch):
    monkeypatch.setattr(blocks, "_hits_semantic_sampling_guard", lambda *_: [])
    store = TextStore(tmp_path)
    out = queue.Queue()
    blocks._process_block(
        {"type": "table", "section_id": "s", "caption": "Table", "columns": ["A"], "rows": [[1]]},
        section="Section", section_id="s", is_reference=False, text_store=store,
        seen=set(), seen_norm=set(), texts=[], plain_lines=[], out_queue=out,
        emitted_chars=0, last_norm="", repeat_streak=0, stop_threshold=0,
    )
    event = out.get_nowait()
    assert store.get_json(event["block_id"])["rows"] == [[1]]
