from __future__ import annotations

from writing_agent.v2.doc_format import parse_report_text
from writing_agent.v2.figure_render import render_figure_svg, score_figure_spec


def test_parse_report_text_repairs_split_table_marker() -> None:
    text = "\n".join(
        [
            "# Sample",
            "",
            "## Results",
            "",
            '[[TABLE:{"caption":"Metrics","columns":["Metric","Value"],"rows":[["Latency","120ms"],["Accuracy","98%"]]',
            "",
            '}]]',
            "",
            "Follow-up paragraph.",
        ]
    )
    parsed = parse_report_text(text)
    table_blocks = [block for block in parsed.blocks if block.type == "table"]
    assert len(table_blocks) == 1
    assert table_blocks[0].table == {
        "caption": "Metrics",
        "columns": ["Metric", "Value"],
        "rows": [["Latency", "120ms"], ["Accuracy", "98%"]],
    }
    leaked = [block for block in parsed.blocks if block.type == "paragraph" and "[[TABLE:" in str(block.text or "")]
    assert not leaked


def test_render_figure_svg_uses_label_and_edge_alias_fields() -> None:
    spec = {
        "type": "flow",
        "caption": "Pipeline",
        "data": {
            "nodes": [
                {"id": "n1", "label": "Task Intake"},
                {"id": "n2", "label": "Evidence Filter"},
                {"id": "n3", "label": "Draft Output"},
            ],
            "edges": [
                {"from": "n1", "to": "n2", "label": "validated"},
                {"from": "n2", "to": "n3", "label": "grounded"},
            ],
        },
    }
    svg, caption = render_figure_svg(spec)
    assert caption == "Pipeline"
    assert "Task Intake" in svg
    assert "Evidence Filter" in svg
    assert "Draft Output" in svg
    assert "validated" in svg
    assert "grounded" in svg
    assert "Microsoft YaHei" in svg


def test_score_figure_spec_penalizes_generic_flow_labels() -> None:
    spec = {
        "type": "flow",
        "caption": "Pipeline",
        "data": {
            "nodes": [
                {"id": "n1", "text": "Step 1"},
                {"id": "n2", "text": "Step 2"},
                {"id": "n3", "text": "Step 3"},
            ],
            "edges": [
                {"src": "n1", "dst": "n2"},
                {"src": "n2", "dst": "n3"},
            ],
        },
    }
    score = score_figure_spec(spec, svg="<svg>" + ("x" * 260) + "</svg>", png_rendered=True)
    assert "flow_labels_generic" in list(score.get("issues") or [])
    assert int(score.get("score") or 0) < 100
