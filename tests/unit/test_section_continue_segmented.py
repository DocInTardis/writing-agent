from __future__ import annotations

import queue

from writing_agent.v2 import graph_section_draft_domain as draft_domain


def _identity_postprocess(
    section: str,
    text: str,
    *,
    min_paras: int,
    min_chars: int,
    max_chars: int,
    min_tables: int,
    min_figures: int,
) -> str:
    _ = section, min_paras, min_chars, max_chars, min_tables, min_figures
    return str(text or "").strip()



def _predict_num_tokens(min_chars: int, max_chars: int, is_reference: bool) -> int:
    _ = min_chars, max_chars, is_reference
    return 256



def test_ensure_section_minimums_stream_uses_segmented_continue(monkeypatch):
    monkeypatch.setenv("WRITING_AGENT_SECTION_CONTINUE_ROUNDS", "1")
    monkeypatch.setenv("WRITING_AGENT_SECTION_CONTINUE_SEGMENT_ENABLED", "1")
    monkeypatch.setenv("WRITING_AGENT_SECTION_CONTINUE_SEGMENT_THRESHOLD_CHARS", "20")
    monkeypatch.setenv("WRITING_AGENT_SECTION_CONTINUE_SEGMENT_TARGET_CHARS", "18")
    monkeypatch.setenv("WRITING_AGENT_SECTION_CONTINUE_SEGMENT_MAX", "2")

    def _provider_factory(*, model: str, timeout_s: float, route_key: str):
        _ = model, timeout_s
        return {"route_key": route_key}

    def _stream_structured_blocks(**kwargs):
        route_key = str((kwargs.get("client") or {}).get("route_key") or "")
        if route_key.endswith(":1"):
            return "第一补充分段，补足方法细节与样本边界。"
        if route_key.endswith(":2"):
            return "第二补充分段，补足区域差异与政策影响。"
        return "单次补齐。"

    out_q: queue.Queue[dict] = queue.Queue()
    text = draft_domain.ensure_section_minimums_stream(
        base_url="http://test",
        model="gpt-5.4",
        title="测试标题",
        section="数据来源与检索策略",
        parent_section="研究设计",
        instruction="写作任务",
        analysis_summary="分析摘要",
        evidence_summary="证据摘要",
        allowed_urls=[],
        plan_hint='{"section":"数据来源与检索策略"}',
        dimension_hints=["样本边界", "方法细节", "区域差异", "政策影响"],
        draft="已有基础段落。",
        min_paras=3,
        min_chars=260,
        max_chars=400,
        min_tables=1,
        min_figures=0,
        out_queue=out_q,
        postprocess_section=_identity_postprocess,
        stream_structured_blocks=_stream_structured_blocks,
        normalize_section_id=lambda _section: "sec_001",
        predict_num_tokens=_predict_num_tokens,
        is_reference_section=lambda _section: False,
        section_timeout_s=lambda: 60.0,
        provider_factory=_provider_factory,
    )

    assert "第一补充分段" in text
    assert "第二补充分段" in text
    assert text.index("第一补充分段") < text.index("第二补充分段")

    events: list[dict] = []
    while True:
        try:
            events.append(out_q.get_nowait())
        except queue.Empty:
            break
    assert any(str(ev.get("event") or "") == "section_continue_segment_plan" for ev in events)
    assert any(str(ev.get("event") or "") == "section_continue_segment" and str(ev.get("phase") or "") == "end" for ev in events)



def test_ensure_section_minimums_stream_segment_failure_falls_back(monkeypatch):
    monkeypatch.setenv("WRITING_AGENT_SECTION_CONTINUE_ROUNDS", "1")
    monkeypatch.setenv("WRITING_AGENT_SECTION_CONTINUE_SEGMENT_ENABLED", "1")
    monkeypatch.setenv("WRITING_AGENT_SECTION_CONTINUE_SEGMENT_THRESHOLD_CHARS", "20")
    monkeypatch.setenv("WRITING_AGENT_SECTION_CONTINUE_SEGMENT_TARGET_CHARS", "18")
    monkeypatch.setenv("WRITING_AGENT_SECTION_CONTINUE_SEGMENT_MAX", "2")

    def _provider_factory(*, model: str, timeout_s: float, route_key: str):
        _ = model, timeout_s
        return {"route_key": route_key}

    def _stream_structured_blocks(**kwargs):
        route_key = str((kwargs.get("client") or {}).get("route_key") or "")
        if route_key.endswith(":2"):
            raise RuntimeError("segment failed")
        if ".continue.segment:" in route_key:
            return "局部分段内容。"
        return "回退后的单次补齐内容，补足全部缺口。"

    out_q: queue.Queue[dict] = queue.Queue()
    text = draft_domain.ensure_section_minimums_stream(
        base_url="http://test",
        model="gpt-5.4",
        title="测试标题",
        section="数据来源与检索策略",
        parent_section="研究设计",
        instruction="写作任务",
        analysis_summary="分析摘要",
        evidence_summary="证据摘要",
        allowed_urls=[],
        plan_hint='{"section":"数据来源与检索策略"}',
        dimension_hints=["样本边界", "方法细节", "区域差异", "政策影响"],
        draft="已有基础段落。",
        min_paras=2,
        min_chars=260,
        max_chars=400,
        min_tables=1,
        min_figures=0,
        out_queue=out_q,
        postprocess_section=_identity_postprocess,
        stream_structured_blocks=_stream_structured_blocks,
        normalize_section_id=lambda _section: "sec_001",
        predict_num_tokens=_predict_num_tokens,
        is_reference_section=lambda _section: False,
        section_timeout_s=lambda: 60.0,
        provider_factory=_provider_factory,
    )

    assert "回退后的单次补齐内容" in text

    events: list[dict] = []
    while True:
        try:
            events.append(out_q.get_nowait())
        except queue.Empty:
            break
    assert any(str(ev.get("event") or "") == "section_continue_segment_fallback" for ev in events)



def test_continue_segment_planning_balances_heavy_focus_points_and_budget(monkeypatch):
    monkeypatch.setenv("WRITING_AGENT_SECTION_CONTINUE_SEGMENT_ENABLED", "1")
    monkeypatch.setenv("WRITING_AGENT_SECTION_CONTINUE_SEGMENT_THRESHOLD_CHARS", "20")
    monkeypatch.setenv("WRITING_AGENT_SECTION_CONTINUE_SEGMENT_TARGET_CHARS", "240")
    monkeypatch.setenv("WRITING_AGENT_SECTION_CONTINUE_SEGMENT_MAX", "3")

    hints = [
        "architecture workflow implementation evidence matrix",
        "framework process interface coordination",
        "data sample policy risk",
        "scope",
        "case",
        "region",
    ]
    buckets = draft_domain._split_focus_points_balanced(hints, 3)
    bucket_weights = [sum(draft_domain._focus_point_weight(item) for item in bucket) for bucket in buckets]
    heavy_hits = [sum(1 for item in bucket if ("architecture" in item or "framework" in item)) for bucket in buckets]

    naive_weights = [
        sum(draft_domain._focus_point_weight(item) for item in group)
        for group in [hints[0:2], hints[2:4], hints[4:6]]
    ]

    assert len(buckets) == 3
    assert max(heavy_hits) == 1
    assert max(bucket_weights) - min(bucket_weights) < max(naive_weights) - min(naive_weights)

    segments = draft_domain._plan_continue_segments(
        section="Method",
        missing_chars=960,
        min_paras=3,
        min_tables=1,
        min_figures=0,
        dimension_hints=hints,
        is_reference_section=lambda _section: False,
    )
    segment_weights = [sum(draft_domain._focus_point_weight(item) for item in (seg.get("focus_points") or [])) for seg in segments]
    segment_budgets = [int(seg.get("missing_chars") or 0) for seg in segments]

    assert len(segments) == 3
    assert sum(segment_budgets) == 960
    assert segment_budgets[segment_weights.index(max(segment_weights))] == max(segment_budgets)
