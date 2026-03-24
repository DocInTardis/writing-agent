from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

import writing_agent.web.app_v2 as app_v2
from writing_agent.v2.diagram_design import enrich_figure_spec, resolve_requested_diagram_kind, suggest_diagram_spec
from writing_agent.v2.figure_render import render_figure_svg


def test_enrich_architecture_spec_promotes_groups_into_lanes() -> None:
    spec = {
        "type": "architecture",
        "caption": "智能写作代理系统总体架构",
        "data": {
            "nodes": [
                {"id": "u", "label": "用户门户", "group": "接入层"},
                {"id": "o", "label": "任务编排中心", "group": "编排层"},
                {"id": "r", "label": "检索服务", "group": "能力层"},
                {"id": "d", "label": "向量索引", "group": "数据层"},
            ],
            "edges": [
                {"from": "u", "to": "o", "label": "任务请求"},
                {"from": "o", "to": "r", "label": "检索调用"},
                {"from": "r", "to": "d", "label": "向量召回"},
            ],
        },
    }
    enriched = enrich_figure_spec(spec)
    lanes = (enriched.get("data") or {}).get("lanes") or []
    titles = [lane.get("title") for lane in lanes if isinstance(lane, dict)]
    assert titles[:4] == ["接入层", "编排层", "能力层", "数据层"]


def test_render_figure_svg_architecture_contains_lane_headers_and_subtitles() -> None:
    spec = {
        "type": "architecture",
        "caption": "智能写作代理系统总体架构",
        "data": {
            "nodes": [
                {"id": "u", "label": "用户门户", "subtitle": "课题提交/状态查看", "lane": "access", "kind": "actor"},
                {"id": "o", "label": "任务编排中心", "subtitle": "章节拆解/依赖调度", "lane": "orchestration", "kind": "service"},
                {"id": "r", "label": "检索服务", "subtitle": "RAG/事实包生成", "lane": "capability", "kind": "service"},
                {"id": "d", "label": "向量索引", "subtitle": "召回缓存", "lane": "data", "kind": "data"},
            ],
            "edges": [
                {"from": "u", "to": "o", "label": "任务请求"},
                {"from": "o", "to": "r", "label": "证据计划"},
                {"from": "r", "to": "d", "label": "向量召回"},
            ],
        },
    }
    svg, caption = render_figure_svg(spec)
    assert caption == "智能写作代理系统总体架构"
    assert "接入层" in svg
    assert "编排层" in svg
    assert "能力层" in svg
    assert "数据层" in svg
    assert "RAG/事实包生成" in svg
    assert "向量召回" in svg


def test_render_figure_svg_sequence_contains_lifeline_and_return_arrow() -> None:
    spec = {
        "type": "sequence",
        "caption": "写作任务处理时序",
        "data": {
            "participants": ["用户", "API网关", "生成服务", "文档服务"],
            "messages": [
                {"from": "用户", "to": "API网关", "label": "提交任务"},
                {"from": "API网关", "to": "生成服务", "label": "创建上下文"},
                {"from": "生成服务", "to": "文档服务", "label": "写入成稿"},
                {"from": "文档服务", "to": "用户", "label": "返回结果", "style": "dashed"},
            ],
        },
    }
    svg, _caption = render_figure_svg(spec)
    assert "用户" in svg
    assert "API网关" in svg
    assert "stroke-dasharray=\"6,6\"" in svg
    assert "stroke-dasharray=\"6,4\"" in svg
    assert "返回结果" in svg


def test_diagram_generate_architecture_uses_richer_fallback(monkeypatch) -> None:
    session = app_v2.store.create()
    app_v2._set_doc_text(session, "# T\n\nseed")
    app_v2.store.put(session)

    monkeypatch.setattr(
        app_v2,
        "get_ollama_settings",
        lambda: SimpleNamespace(enabled=False, base_url="http://test", model="m", timeout_s=3.0),
    )

    client = TestClient(app_v2.app)
    resp = client.post(
        f"/api/doc/{session.id}/diagram/generate",
        json={"prompt": "论文写作代理系统总体架构", "kind": "architecture"},
    )
    assert resp.status_code == 200
    spec = (resp.json() or {}).get("spec") or {}
    assert spec.get("type") == "architecture"
    data = spec.get("data") or {}
    lanes = data.get("lanes") or []
    assert len(lanes) >= 3
    assert any((lane.get("title") if isinstance(lane, dict) else "") == "能力层" for lane in lanes)
    nodes = data.get("nodes") or []
    assert any((node.get("subtitle") if isinstance(node, dict) else "") for node in nodes)





def test_enrich_figure_spec_infers_pie_from_caption_semantics() -> None:
    enriched = enrich_figure_spec({"caption": "Topic Share of Research Themes"}, section_title="Results")
    assert enriched.get("type") == "pie"
    data = enriched.get("data") or {}
    assert len(data.get("segments") or []) >= 3


def test_resolve_requested_diagram_kind_upgrades_generic_flow_by_caption_semantics() -> None:
    kind = resolve_requested_diagram_kind("flow", caption="Research Timeline", prompt="Roadmap of milestones")
    assert kind == "timeline"


def test_suggest_diagram_spec_upgrades_generic_flow_to_timeline() -> None:
    spec = suggest_diagram_spec("flow", caption="Research Timeline", prompt="Roadmap of milestones")
    assert spec.get("type") == "timeline"
    assert len(((spec.get("data") or {}).get("events") or [])) >= 2


def test_enrich_figure_spec_upgrades_generic_flow_to_timeline() -> None:
    enriched = enrich_figure_spec(
        {"type": "flow", "caption": "Research Timeline", "data": {}},
        section_title="Implementation Roadmap",
    )
    assert enriched.get("type") == "timeline"
    data = enriched.get("data") or {}
    assert len(data.get("events") or []) >= 2

def test_render_figure_svg_er_uses_professional_entity_cards() -> None:
    spec = {
        "type": "er",
        "caption": "Research Writing Entity Graph",
        "data": {
            "entities": [
                {"name": "User", "attributes": ["user_id", "name", "role"]},
                {"name": "Project", "attributes": ["project_id", "title", "discipline"]},
                {"name": "Document", "attributes": ["doc_id", "status", "version"]},
            ],
            "relations": [
                {"left": "User", "right": "Project", "label": "owns", "cardinality": "1:N"},
                {"left": "Project", "right": "Document", "label": "produces", "cardinality": "1:N"},
            ],
        },
    }
    svg, caption = render_figure_svg(spec)
    assert caption == "Research Writing Entity Graph"
    assert "User" in svg
    assert "Project" in svg
    assert "Document" in svg
    assert "1:N" in svg
    assert "produces" in svg

def test_render_figure_svg_er_renders_crow_foot_cardinality_markers() -> None:
    spec = {
        "type": "er",
        "caption": "Entity Cardinality Overview",
        "data": {
            "entities": [
                {"name": "Order", "attributes": ["order_id", "created_at"]},
                {"name": "LineItem", "attributes": ["item_id", "sku"]},
            ],
            "relations": [
                {"left": "Order", "right": "LineItem", "label": "contains", "cardinality": "0:N"},
            ],
        },
    }
    svg, _caption = render_figure_svg(spec)
    assert 'class="crow-zero"' in svg
    assert 'class="crow-many"' in svg
    assert "contains" in svg


def test_render_figure_svg_bar_uses_chart_card_and_value_labels() -> None:
    spec = {
        "type": "bar",
        "caption": "Key Metrics Comparison",
        "data": {"labels": ["Retrieval Hit Rate", "Citation Precision", "Export Success"], "values": [81, 92, 98]},
    }
    svg, _caption = render_figure_svg(spec)
    assert "Key Metrics Comparison" in svg
    assert "Retrieval" in svg
    assert "Hit" in svg
    assert "92" in svg
    assert "98" in svg


def test_render_figure_svg_line_uses_legend_and_points() -> None:
    spec = {
        "type": "line",
        "caption": "Quality Trend",
        "data": {
            "labels": ["T1", "T2", "T3", "T4"],
            "series": [
                {"name": "Consistency", "values": [72, 78, 84, 88]},
                {"name": "Citation Coverage", "values": [66, 71, 79, 85]},
            ],
        },
    }
    svg, _caption = render_figure_svg(spec)
    assert "Quality Trend" in svg
    assert "Consistency" in svg
    assert "Citation" in svg
    assert "circle" in svg


def test_render_figure_svg_pie_uses_total_and_percent_labels() -> None:
    spec = {
        "type": "pie",
        "caption": "Topic Share",
        "data": {
            "segments": [
                {"label": "Retrieval", "value": 35},
                {"label": "Generation", "value": 30},
                {"label": "Validation", "value": 20},
                {"label": "Export", "value": 15},
            ]
        },
    }
    svg, _caption = render_figure_svg(spec)
    assert "Topic Share" in svg
    assert "Total" in svg
    assert "%" in svg
    assert "Retrieval" in svg


def test_render_figure_svg_timeline_uses_cards_and_axis() -> None:
    spec = {
        "type": "timeline",
        "caption": "Research Timeline",
        "data": {
            "events": [
                {"time": "2026.01", "label": "Problem Scoping"},
                {"time": "2026.02", "label": "Evidence Cleaning"},
                {"time": "2026.03", "label": "Cluster Analysis"},
            ]
        },
    }
    svg, _caption = render_figure_svg(spec)
    assert "Research Timeline" in svg
    assert "2026.01" in svg
    assert "Evidence" in svg
    assert "Cleaning" in svg
    assert 'stroke-dasharray="4,4"' in svg
