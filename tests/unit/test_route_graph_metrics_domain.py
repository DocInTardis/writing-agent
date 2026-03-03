import json

from writing_agent.web.domains import route_graph_metrics_domain as rgm


def _read_jsonl(path):
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        out.append(json.loads(line))
    return out


def test_route_graph_metrics_write_row(monkeypatch, tmp_path):
    metrics_path = tmp_path / "route_graph_events.jsonl"
    monkeypatch.setenv("WRITING_AGENT_ROUTE_GRAPH_METRICS_ENABLE", "1")
    monkeypatch.setenv("WRITING_AGENT_ROUTE_GRAPH_METRICS_PATH", str(metrics_path))

    rgm.record_route_graph_metric(
        "graph_failed",
        phase="generate",
        path="route_graph",
        route_id="resume_sections",
        route_entry="writer",
        engine="native",
        fallback_triggered=True,
        fallback_recovered=False,
        error_code="E_INJECTED_ROUTE_GRAPH_FAILURE",
        elapsed_ms=12.5,
        extra={"k": "v"},
    )

    rows = _read_jsonl(metrics_path)
    assert rows
    row = rows[-1]
    assert str(row.get("event") or "") == "graph_failed"
    assert str(row.get("phase") or "") == "generate"
    assert str(row.get("route_id") or "") == "resume_sections"
    assert bool(row.get("fallback_triggered")) is True
    assert bool(row.get("fallback_recovered")) is False
    assert str(row.get("error_code") or "") == "E_INJECTED_ROUTE_GRAPH_FAILURE"


def test_route_graph_failure_injection_phase_filter(monkeypatch):
    monkeypatch.setenv("WRITING_AGENT_FAIL_INJECT_ROUTE_GRAPH", "1")
    monkeypatch.setenv("WRITING_AGENT_FAIL_INJECT_ROUTE_GRAPH_PHASES", "generate_stream")
    assert rgm.should_inject_route_graph_failure(phase="generate") is False
    assert rgm.should_inject_route_graph_failure(phase="generate_stream") is True

