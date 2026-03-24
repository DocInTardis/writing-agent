from __future__ import annotations

import json

import writing_agent.v2.graph_runner as graph_runner


def test_format_plan_hint_drops_section_role_and_meta_key_points():
    plan = graph_runner.PlanSection(
        title="引言",
        target_chars=900,
        min_chars=600,
        max_chars=1200,
        min_tables=0,
        min_figures=0,
        key_points=[
            "摘要应覆盖研究目标、范围边界、关键约束与可量化产出",
            "说明区块链在农村社会化服务协同治理中的核心机制",
        ],
        figures=[],
        tables=[],
        evidence_queries=[],
    )
    raw = graph_runner._format_plan_hint(plan)
    payload = json.loads(raw)
    assert "section_role" not in payload
    points = list(payload.get("key_points") or [])
    assert len(points) == 1
    assert "区块链" in points[0]

