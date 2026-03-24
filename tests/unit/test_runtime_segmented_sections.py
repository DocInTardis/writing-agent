from __future__ import annotations

import json
import queue
import threading
import time

from writing_agent.v2 import graph_runner_runtime as runtime_module
from writing_agent.v2.section_contract import SectionContractSpec


def _build_plan(*, target_chars: int = 1800) -> runtime_module.PlanSection:
    return runtime_module.PlanSection(
        title="数据来源与检索策略",
        target_chars=target_chars,
        min_chars=target_chars,
        max_chars=2400,
        min_tables=1,
        min_figures=0,
        key_points=[
            "数据来源范围",
            "检索策略与筛选条件",
            "样本边界与时间窗口",
            "质量控制与去重规则",
            "区域差异比较",
            "政策影响分析",
        ],
        figures=[],
        tables=[],
        evidence_queries=["区块链 农村 社会化服务", "CiteSpace 可视化分析"],
    )



def _build_targets(*, min_chars: int = 1800, max_chars: int = 2400) -> runtime_module.SectionTargets:
    return runtime_module.SectionTargets(
        weight=1.0,
        min_paras=4,
        min_chars=min_chars,
        max_chars=max_chars,
        min_tables=1,
        min_figures=0,
    )



def _build_contract() -> SectionContractSpec:
    return SectionContractSpec(
        section="数据来源与检索策略",
        min_chars=1800,
        max_chars=2400,
        min_paras=4,
        required_slots=[],
        dimension_hints=["区域差异与场景边界", "政策影响与治理机制"],
    )



def _base_stream_kwargs() -> dict[str, object]:
    return {
        "base_url": "http://test",
        "model": "m",
        "title": "测试标题",
        "section": "研究设计 / 数据来源与检索策略",
        "section_id_override": "sec_data_sources",
        "parent_section": "研究设计",
        "instruction": "写一篇关于区块链赋能农村社会化服务的中文论文",
        "plan_hint": json.dumps({"section_title": "数据来源与检索策略", "key_points": ["总体说明"]}, ensure_ascii=False),
        "analysis_summary": "围绕区块链与农村社会化服务展开",
        "evidence_summary": "包含文献检索流程、样本边界和数据来源说明",
        "allowed_urls": [],
        "reference_items": [],
        "min_paras": 4,
        "min_chars": 1800,
        "max_chars": 2400,
        "min_tables": 1,
        "min_figures": 0,
    }



def _drain_events(q: queue.Queue[dict]) -> list[dict]:
    out: list[dict] = []
    while True:
        try:
            out.append(q.get_nowait())
        except queue.Empty:
            break
    return out



def test_plan_section_segments_only_for_oversized_non_reference(monkeypatch):
    monkeypatch.setenv("WRITING_AGENT_SECTION_SEGMENT_ENABLED", "1")
    monkeypatch.setenv("WRITING_AGENT_SECTION_SEGMENT_THRESHOLD_CHARS", "1200")
    monkeypatch.setenv("WRITING_AGENT_SECTION_SEGMENT_TARGET_CHARS", "700")
    monkeypatch.setenv("WRITING_AGENT_SECTION_SEGMENT_MAX", "3")

    plan = _build_plan(target_chars=1800)
    contract = _build_contract()
    targets = _build_targets(min_chars=1800, max_chars=2400)

    segments = runtime_module._plan_section_segments(
        section_key="数据来源与检索策略",
        section_title="数据来源与检索策略",
        plan=plan,
        contract=contract,
        targets=targets,
    )
    assert len(segments) == 3
    assert sum(int(item.get("min_chars") or 0) for item in segments) == 1800
    assert int(segments[0].get("min_tables") or 0) == 1
    assert int(segments[1].get("min_tables") or 0) == 0
    assert all(int(item.get("segment_index") or 0) == idx + 1 for idx, item in enumerate(segments))

    assert runtime_module._plan_section_segments(
        section_key="参考文献",
        section_title="参考文献",
        plan=plan,
        contract=contract,
        targets=targets,
    ) == []

    short_contract = SectionContractSpec(
        section="introduction",
        min_chars=700,
        max_chars=1000,
        min_paras=3,
        required_slots=[],
        dimension_hints=["background", "research value"],
    )
    short_plan = runtime_module.PlanSection(
        title="introduction",
        target_chars=700,
        min_chars=700,
        max_chars=1000,
        min_tables=0,
        min_figures=0,
        key_points=["background"],
        figures=[],
        tables=[],
        evidence_queries=[],
    )
    short_segments = runtime_module._plan_section_segments(
        section_key="introduction",
        section_title="introduction",
        plan=short_plan,
        contract=short_contract,
        targets=_build_targets(min_chars=700, max_chars=1000),
    )
    assert short_segments == []

    compact_contract = SectionContractSpec(
        section="data source and search strategy",
        min_chars=440,
        max_chars=715,
        min_paras=4,
        required_slots=[],
        dimension_hints=["regional boundaries", "policy implications"],
    )
    compact_plan = runtime_module.PlanSection(
        title="data source and search strategy",
        target_chars=440,
        min_chars=440,
        max_chars=715,
        min_tables=1,
        min_figures=0,
        key_points=[
            "data scope",
            "search filters",
            "sample window",
            "dedup rules",
        ],
        figures=[],
        tables=[],
        evidence_queries=["blockchain rural services", "CiteSpace parameter setup"],
    )
    compact_segments = runtime_module._plan_section_segments(
        section_key="data source and search strategy",
        section_title="data source and search strategy",
        plan=compact_plan,
        contract=compact_contract,
        targets=runtime_module.SectionTargets(
            weight=1.0,
            min_paras=4,
            min_chars=440,
            max_chars=715,
            min_tables=1,
            min_figures=0,
        ),
    )
    assert len(compact_segments) >= 2


def test_draft_section_with_optional_segments_merges_results_in_order(monkeypatch):
    monkeypatch.setenv("WRITING_AGENT_SECTION_SEGMENT_ENABLED", "1")
    monkeypatch.setenv("WRITING_AGENT_SECTION_SEGMENT_THRESHOLD_CHARS", "1200")
    monkeypatch.setenv("WRITING_AGENT_SECTION_SEGMENT_TARGET_CHARS", "700")
    monkeypatch.setenv("WRITING_AGENT_SECTION_SEGMENT_MAX", "3")

    def _fake_generate_section_stream(**kwargs):
        payload = json.loads(str(kwargs.get("plan_hint") or "{}") or "{}")
        idx = int(payload.get("segment_index") or 0)
        kwargs["out_queue"].put({"event": "prompt_route", "stage": "writer_section", "segment_index": idx})
        return f"part-{idx}"

    monkeypatch.setattr(runtime_module, "_generate_section_stream", _fake_generate_section_stream)
    q: queue.Queue[dict] = queue.Queue()

    text, used_segment_split = runtime_module._draft_section_with_optional_segments(
        section_key="数据来源与检索策略",
        section_title="数据来源与检索策略",
        section_id="sec_data_sources",
        plan=_build_plan(target_chars=1800),
        contract=_build_contract(),
        targets=_build_targets(min_chars=1800, max_chars=2400),
        out_queue=q,
        text_store=None,
        stream_kwargs=_base_stream_kwargs(),
    )

    assert used_segment_split is True
    assert text == "part-1\n\npart-2\n\npart-3"
    events = _drain_events(q)
    assert any(str(ev.get("event") or "") == "section_segment_plan" for ev in events)
    assert any(str(ev.get("event") or "") == "prompt_route" and int(ev.get("segment_index") or 0) == 1 for ev in events)



def test_draft_section_with_optional_segments_falls_back_to_single_pass(monkeypatch):
    monkeypatch.setenv("WRITING_AGENT_SECTION_SEGMENT_ENABLED", "1")
    monkeypatch.setenv("WRITING_AGENT_SECTION_SEGMENT_THRESHOLD_CHARS", "1200")
    monkeypatch.setenv("WRITING_AGENT_SECTION_SEGMENT_TARGET_CHARS", "700")
    monkeypatch.setenv("WRITING_AGENT_SECTION_SEGMENT_MAX", "3")

    calls: list[int | None] = []

    def _fake_generate_section_stream(**kwargs):
        payload = json.loads(str(kwargs.get("plan_hint") or "{}") or "{}")
        idx = payload.get("segment_index")
        calls.append(int(idx) if idx is not None else None)
        if idx == 2:
            raise RuntimeError("segment exploded")
        return "single-pass" if idx is None else f"segment-{idx}"

    monkeypatch.setattr(runtime_module, "_generate_section_stream", _fake_generate_section_stream)
    q: queue.Queue[dict] = queue.Queue()

    text, used_segment_split = runtime_module._draft_section_with_optional_segments(
        section_key="数据来源与检索策略",
        section_title="数据来源与检索策略",
        section_id="sec_data_sources",
        plan=_build_plan(target_chars=1800),
        contract=_build_contract(),
        targets=_build_targets(min_chars=1800, max_chars=2400),
        out_queue=q,
        text_store=None,
        stream_kwargs=_base_stream_kwargs(),
    )

    assert used_segment_split is False
    assert text == "single-pass"
    assert calls[-1] is None
    events = _drain_events(q)
    assert any(str(ev.get("event") or "") == "section_segment_fallback" for ev in events)



def test_generation_slot_serializes_nested_calls(monkeypatch):
    monkeypatch.setenv("WRITING_AGENT_GENERATION_SLOT_ENABLED", "1")
    monkeypatch.setenv("WRITING_AGENT_GENERATION_SLOT_LIMIT", "1")
    runtime_module._GENERATION_SLOT_MAP.clear()

    active = 0
    max_active = 0
    lock = threading.Lock()
    results: list[str] = []

    def _work() -> str:
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.05)
        with lock:
            active -= 1
        return "ok"

    def _runner() -> None:
        results.append(
            runtime_module._call_with_generation_slot(
                provider_name="openai",
                model="gpt-5.4",
                fn=_work,
                stage="stream",
            )
        )

    t1 = threading.Thread(target=_runner)
    t2 = threading.Thread(target=_runner)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert results == ["ok", "ok"]
    assert max_active == 1
