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


def test_resolve_requested_diagram_kind_can_pick_state_from_semantics() -> None:
    kind = resolve_requested_diagram_kind("flow", caption="审批状态图", prompt="展示任务从草稿到发布的状态流转")
    assert kind == "state"


def test_resolve_requested_diagram_kind_can_pick_mindmap_from_semantics() -> None:
    kind = resolve_requested_diagram_kind("flow", caption="论文主题思维导图", prompt="展示研究主题的背景、方法、实验与结论")
    assert kind == "mindmap"


def test_render_figure_svg_state_renders_states_and_transitions() -> None:
    spec = {
        "type": "state",
        "caption": "Approval State",
        "data": {
            "states": [
                {"id": "draft", "label": "Draft", "kind": "start"},
                {"id": "review", "label": "Review"},
                {"id": "done", "label": "Done", "kind": "end"},
            ],
            "transitions": [
                {"from": "draft", "to": "review", "label": "submit"},
                {"from": "review", "to": "done", "label": "approve"},
            ],
        },
    }
    svg, caption = render_figure_svg(spec)
    assert caption == "Approval State"
    assert "Draft" in svg
    assert "Review" in svg
    assert "approve" in svg
    assert "stateArrow" in svg


def test_render_figure_svg_class_renders_cards_and_relations() -> None:
    spec = {
        "type": "class",
        "caption": "Domain Classes",
        "data": {
            "classes": [
                {"name": "Project", "attributes": ["id", "title"], "methods": ["create()"]},
                {"name": "Document", "attributes": ["id", "status"], "methods": ["publish()"]},
            ],
            "relations": [{"from": "Project", "to": "Document", "label": "contains", "kind": "association"}],
        },
    }
    svg, caption = render_figure_svg(spec)
    assert caption == "Domain Classes"
    assert "Project" in svg
    assert "Document" in svg
    assert "contains" in svg
    assert "classArrow" in svg


def test_render_figure_svg_gantt_renders_tasks_and_statuses() -> None:
    spec = {
        "type": "gantt",
        "caption": "Implementation Plan",
        "data": {
            "tasks": [
                {"task": "Scoping", "start": "M1", "end": "M2", "status": "done"},
                {"task": "Build", "start": "M2", "end": "M4", "status": "active"},
                {"task": "Review", "start": "M4", "end": "M5", "status": "planned"},
            ]
        },
    }
    svg, caption = render_figure_svg(spec)
    assert caption == "Implementation Plan"
    assert "Scoping" in svg
    assert "Build" in svg
    assert "planned" in svg
    assert "M1" in svg


def test_render_figure_svg_mindmap_renders_center_and_branches() -> None:
    spec = {
        "type": "mindmap",
        "caption": "Research Mind Map",
        "data": {
            "center": "Writing Agent",
            "branches": [
                {"label": "Background", "children": ["Gap", "Need"]},
                {"label": "Method", "children": ["RAG", "Validation"]},
                {"label": "Experiment", "children": ["Metrics"]},
            ],
        },
    }
    svg, caption = render_figure_svg(spec)
    assert caption == "Research Mind Map"
    assert "Writing Agent" in svg
    assert "Background" in svg
    assert "RAG" in svg


def test_render_figure_svg_quadrant_renders_matrix_items() -> None:
    spec = {
        "type": "quadrant",
        "caption": "Priority Matrix",
        "data": {
            "x_axis": "Impact",
            "y_axis": "Feasibility",
            "items": [
                {"label": "Core Feature", "x": 0.8, "y": 0.8},
                {"label": "Backlog", "x": 0.2, "y": 0.2},
            ],
        },
    }
    svg, caption = render_figure_svg(spec)
    assert caption == "Priority Matrix"
    assert "Impact" in svg
    assert "Feasibility" in svg
    assert "Core Feature" in svg
    assert "Q1" in svg


def test_render_figure_svg_radar_renders_axes_and_polygon() -> None:
    spec = {
        "type": "radar",
        "caption": "Capability Profile",
        "data": {
            "axes": ["Quality", "Coverage", "Speed", "Cost"],
            "series": [{"name": "Model A", "values": [82, 74, 88, 69]}],
        },
    }
    svg, caption = render_figure_svg(spec)
    assert caption == "Capability Profile"
    assert "Quality" in svg
    assert "Model A" in svg
    assert "polygon" in svg


def test_render_figure_svg_scatter_renders_points_and_axes() -> None:
    spec = {
        "type": "scatter",
        "caption": "Cost Performance Scatter",
        "data": {
            "x_label": "Cost",
            "y_label": "Performance",
            "points": [
                {"label": "A", "x": 12, "y": 68, "group": "baseline"},
                {"label": "B", "x": 44, "y": 86, "group": "improved"},
            ],
        },
    }
    svg, caption = render_figure_svg(spec)
    assert caption == "Cost Performance Scatter"
    assert "Cost" in svg
    assert "Performance" in svg
    assert "A" in svg
    assert "circle" in svg


def test_render_figure_svg_heatmap_renders_matrix() -> None:
    spec = {
        "type": "heatmap",
        "caption": "热力图",
        "data": {
            "rows": ["方法", "实验"],
            "cols": ["风险", "优先级"],
            "values": [[65, 82], [44, 73]],
        },
    }
    svg, caption = render_figure_svg(spec)
    assert caption == "热力图"
    assert "方法" in svg
    assert "优先级" in svg
    assert "82" in svg


def test_render_figure_svg_funnel_renders_stages() -> None:
    spec = {
        "type": "funnel",
        "caption": "漏斗图",
        "data": {
            "stages": [
                {"label": "原始候选", "value": 120},
                {"label": "筛选后", "value": 80},
                {"label": "最终采用", "value": 30},
            ]
        },
    }
    svg, caption = render_figure_svg(spec)
    assert caption == "漏斗图"
    assert "原始候选" in svg
    assert "30" in svg
    assert "polygon" in svg


def test_render_figure_svg_sankey_renders_nodes_and_links() -> None:
    spec = {
        "type": "sankey",
        "caption": "桑基图",
        "data": {
            "nodes": ["输入", "处理", "输出"],
            "links": [
                {"source": "输入", "target": "处理", "value": 100},
                {"source": "处理", "target": "输出", "value": 60},
            ],
        },
    }
    svg, caption = render_figure_svg(spec)
    assert caption == "桑基图"
    assert "输入" in svg
    assert "输出" in svg
    assert "path" in svg


def test_render_figure_svg_swot_renders_four_quadrants() -> None:
    spec = {
        "type": "swot",
        "caption": "SWOT图",
        "data": {
            "strengths": ["效率高"],
            "weaknesses": ["成本高"],
            "opportunities": ["市场增长"],
            "threats": ["竞争激烈"],
        },
    }
    svg, caption = render_figure_svg(spec)
    assert caption == "SWOT图"
    assert "优势 Strengths" in svg
    assert "威胁 Threats" in svg
    assert "效率高" in svg
