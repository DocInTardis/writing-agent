from __future__ import annotations

from writing_agent.v2 import graph_section_draft_domain as section_domain
from writing_agent.v2.figure_render import export_rendered_figure_assets, extract_figure_specs, score_figure_spec


def test_score_figure_spec_recognizes_supported_dense_chart(tmp_path) -> None:
    _ = tmp_path
    spec = {
        "type": "bar",
        "caption": "服务效率对比",
        "data": {"labels": ["A", "B", "C"], "values": [1, 2, 3]},
    }
    score = score_figure_spec(spec, svg="<svg>" + ("x" * 260) + "</svg>", png_rendered=True)
    assert int(score.get("score") or 0) >= 75
    assert bool(score.get("passed")) is True
    assert str(score.get("recommendation") or "") == "keep"


def test_export_rendered_figure_assets_includes_score_summary_and_duplicate_penalty(tmp_path) -> None:
    text = "\n".join(
        [
            '[[FIGURE:{"type":"bar","caption":"服务效率对比","data":{"labels":["甲","乙","丙"],"values":[1,2,3]}}]]',
            '[[FIGURE:{"type":"bar","caption":"服务效率对比","data":{"labels":["甲","乙","丙"],"values":[1,2,3]}}]]',
            '[[FIGURE:{"type":"unknown","caption":"图 1","data":{}}]]',
        ]
    )
    manifest = export_rendered_figure_assets(text, tmp_path / "figure_assets")
    items = manifest.get("items") or []
    assert len(items) == 3
    assert "avg_score" in manifest
    assert "min_score" in manifest
    assert "max_score" in manifest
    assert "passed_count" in manifest
    assert int(items[1].get("score") or 0) < int(items[0].get("score") or 0)
    assert "duplicate_caption" in list(items[1].get("issues") or [])
    assert str(items[2].get("recommendation") or "") in {"review", "drop"}



def test_extract_figure_specs_require_renderable_filters_caption_only_markers() -> None:
    text = "\n".join(
        [
            '[[FIGURE:{"caption":"?1"}]]',
            '[[FIGURE:{"type":"architecture","caption":"?????","data":{"nodes":["??","??","??"],"edges":[["??","??"],["??","??"]]}}]]',
        ]
    )
    all_specs = extract_figure_specs(text)
    valid_specs = extract_figure_specs(text, require_renderable=True)
    assert len(all_specs) == 2
    assert len(valid_specs) == 1
    assert str(valid_specs[0].get("type") or "") == "architecture"



class _CaptureStore:
    def __init__(self) -> None:
        self.payload = None
        self.prefix = None

    def put_json(self, payload, *, block_id=None, prefix=""):
        _ = block_id
        self.payload = dict(payload)
        self.prefix = prefix
        return "stored"


def test_render_block_to_text_preserves_figure_kind_as_marker_type() -> None:
    text = section_domain.render_block_to_text(
        {
            "type": "figure",
            "kind": "architecture",
            "caption": "System architecture",
            "data": {"nodes": ["A", "B"], "edges": [["A", "B"]]},
        }
    )
    assert '"type": "architecture"' in text or '"type":"architecture"' in text



def test_persist_block_to_store_preserves_figure_kind_as_payload_type() -> None:
    store = _CaptureStore()
    stored_id = section_domain.persist_block_to_store(
        {
            "type": "figure",
            "kind": "architecture",
            "caption": "System architecture",
            "data": {"nodes": ["A", "B"], "edges": [["A", "B"]]},
        },
        store,
    )
    assert stored_id == "stored"
    assert store.prefix == "f"
    assert isinstance(store.payload, dict)
    assert store.payload.get("type") == "architecture"



def test_score_figure_spec_penalizes_caption_kind_mismatch() -> None:
    spec = {
        "type": "flow",
        "caption": "Topic Share of Research Themes",
        "data": {
            "nodes": [
                {"id": "n1", "label": "Collect Data"},
                {"id": "n2", "label": "Analyze Evidence"},
                {"id": "n3", "label": "Export Draft"},
            ],
            "edges": [
                {"from": "n1", "to": "n2"},
                {"from": "n2", "to": "n3"},
            ],
        },
    }
    score = score_figure_spec(spec, svg="<svg>" + ("x" * 520) + "</svg>", png_rendered=True)
    assert "caption_kind_mismatch" in list(score.get("issues") or [])
    breakdown = score.get("breakdown") or {}
    assert int(breakdown.get("consistency") or 0) < 10
