from __future__ import annotations

from types import SimpleNamespace

from writing_agent.v2 import graph_runner_runtime as runtime_module
from writing_agent.v2.graph_runner import GenerateConfig


def _patch_runtime_common(monkeypatch) -> None:
    monkeypatch.setattr(runtime_module, "get_provider_name", lambda: "openai")
    monkeypatch.setattr(runtime_module, "get_provider_snapshot", lambda: {"provider": "openai", "base_url": "https://example.test/v1"})
    monkeypatch.setattr(runtime_module, "get_default_provider", lambda **_kwargs: object())
    monkeypatch.setattr(runtime_module, "_provider_preflight", lambda **_kwargs: (True, ""))
    monkeypatch.setattr(runtime_module, "get_ollama_settings", lambda: SimpleNamespace(enabled=True, base_url="http://test", model="m", timeout_s=3.0))
    monkeypatch.setattr(runtime_module, "_analysis_correctness_guard", lambda **_kwargs: (True, [], {}))
    monkeypatch.setattr(runtime_module, "_light_self_check", lambda **_kwargs: [])
    monkeypatch.setattr(
        runtime_module,
        "_analyze_instruction",
        lambda **_kwargs: {
            "topic": "blockchain rural services",
            "doc_type": "academic",
            "audience": "researcher",
            "style": "formal",
            "keywords": ["blockchain", "rural services"],
            "must_include": [],
            "constraints": [],
            "_confidence_score": 0.98,
            "_schema_valid": True,
            "_needs_clarification": False,
        },
    )
    monkeypatch.setattr(
        runtime_module,
        "_classify_paradigm",
        lambda **_kwargs: {
            "paradigm": "",
            "runner_up": "",
            "confidence": 0.95,
            "margin": 0.8,
            "source": "classifier",
            "reasons": ["test"],
            "low_confidence": False,
            "score_map": {},
        },
    )
    monkeypatch.setenv("WRITING_AGENT_ENABLE_RUNTIME_JSON_CACHE", "0")
    monkeypatch.setenv("WRITING_AGENT_FAST_PLAN", "1")
    monkeypatch.setenv("WRITING_AGENT_FAST_DRAFT", "1")
    monkeypatch.setenv("WRITING_AGENT_STRICT_JSON", "0")
    monkeypatch.setenv("WRITING_AGENT_MIN_H2_COUNT", "1")
    monkeypatch.setenv("WRITING_AGENT_MIN_REFERENCE_ITEMS", "4")
    monkeypatch.setenv("WRITING_AGENT_ENFORCE_REFERENCE_MIN", "1")
    monkeypatch.setenv("WRITING_AGENT_ENFORCE_FINAL_VALIDATION", "0")
    monkeypatch.setenv("WRITING_AGENT_ENFORCE_META_FIREWALL", "0")
    monkeypatch.setenv("WRITING_AGENT_ENFORCE_CONTRACT_SLOTS", "0")
    monkeypatch.setenv("WRITING_AGENT_EVIDENCE_ENABLED", "1")
    monkeypatch.setenv("WRITING_AGENT_RAG_THEME_GATE_ENABLED", "0")
    monkeypatch.setenv("WRITING_AGENT_FORCE_REQUIRED_OUTLINE_ONLY", "0")
    monkeypatch.setenv("WRITING_AGENT_REQUIRED_OUTLINE_ONLY", "0")


def test_runtime_reference_repair_and_status_split(monkeypatch):
    _patch_runtime_common(monkeypatch)

    def _build_evidence_pack(**kwargs):
        section = str(kwargs.get("section") or "")
        if "References" in section:
            return {
                "summary": "",
                "sources": [],
                "allowed_urls": [],
                "data_starvation": {"is_starved": False, "stub_mode": False},
                "facts": [],
                "fact_gain_count": 0,
                "fact_density_score": 0.0,
                "online_hits": 0,
            }
        return {
            "summary": "Evidence: blockchain can improve rural service coordination.",
            "sources": [
                {
                    "id": "src-1",
                    "title": "Blockchain for Rural Socialized Service",
                    "url": "https://example.test/1",
                    "authors": ["A. Author"],
                    "published": "2024-01-01",
                    "updated": "2024-01-01",
                    "source": "openalex",
                }
            ],
            "allowed_urls": ["https://example.test/1"],
            "data_starvation": {"is_starved": False, "stub_mode": False},
            "facts": [{"claim": "blockchain can improve rural service coordination", "source": "https://example.test/1"}],
            "fact_gain_count": 1,
            "fact_density_score": 0.2,
            "online_hits": 1,
        }

    monkeypatch.setattr(runtime_module, "_build_evidence_pack", _build_evidence_pack)
    monkeypatch.setattr(
        runtime_module,
        "_fallback_reference_sources",
        lambda **_kwargs: [
            {
                "id": "src-2",
                "title": "Distributed Ledger in Rural Governance",
                "url": "https://example.test/2",
                "authors": ["B. Author"],
                "published": "2023-01-01",
                "updated": "2023-01-01",
                "source": "openalex",
            },
            {
                "id": "src-3",
                "title": "Smart Contract for Agricultural Services",
                "url": "https://example.test/3",
                "authors": ["C. Author"],
                "published": "2022-01-01",
                "updated": "2022-01-01",
                "source": "openalex",
            },
        ],
    )
    monkeypatch.setattr(
        runtime_module,
        "_fast_fill_section",
        lambda section, **_kwargs: (
            "Blockchain improves traceability, service coordination, auditability, and cross-party trust in rural socialized services. "
            "It also supports transparent scheduling, contract execution, and accountability across villages, cooperatives, and service providers."
            if ("References" not in str(section) and "????" not in str(section))
            else ""
        ),
    )

    events = list(
        runtime_module.run_generate_graph(
            instruction="Write an academic paper about blockchain and rural socialized services.",
            current_text="",
            required_h2=["Introduction", "References"],
            required_outline=[(2, "Introduction"), (2, "References")],
            expand_outline=False,
            config=GenerateConfig(workers=1, min_total_chars=1200),
        )
    )

    repair_events = [ev for ev in events if isinstance(ev, dict) and str(ev.get("event") or "") == "reference_repair"]
    assert repair_events
    assert "before_count" in repair_events[-1]
    assert "after_count" in repair_events[-1]
    assert str(repair_events[-1].get("query") or "").strip()

    final = [ev for ev in events if isinstance(ev, dict) and str(ev.get("event") or "") == "final"][-1]
    assert str(final.get("status") or "") == "failed"
    assert str(final.get("runtime_status") or "") == "success"
    assert bool(final.get("quality_passed")) is False
    assert str(final.get("quality_failure_reason") or "") == "reference_items_insufficient"
    snapshot = final.get("quality_snapshot") if isinstance(final.get("quality_snapshot"), dict) else {}
    assert str(snapshot.get("runtime_status") or "") == "success"
    assert int(snapshot.get("reference_item_count") or 0) == 3


def test_derive_reference_query_prefers_instruction_title_when_analysis_is_schema_polluted() -> None:
    instruction = (
        '请围绕《区块链赋能农村社会化服务的CiteSpace可视化分析》生成一篇中文学术论文。'
        '必须提供 1 个 [[FIGURE:{"caption":"研究流程图","kind":"flow","data":{"nodes":[]}}]]，'
        '禁止输出除最终正文外的说明，并确保 caption kind data json 字段完整。'
    )
    query = runtime_module._derive_reference_query(
        analysis={
            'topic': 'figure caption kind data json figure caption kind data json',
            'keywords': ['figure', 'caption', 'kind', 'data', 'json'],
        },
        analysis_summary='',
        instruction=instruction,
    )
    lowered = query.lower()
    assert 'figure' not in lowered
    assert 'caption' not in lowered
    assert 'kind' not in lowered
    assert 'data' not in lowered
    assert 'json' not in lowered
    assert '区块链' in query
    assert '农村' in query
    assert 'citespace' in lowered


def test_derive_reference_query_falls_back_to_clean_instruction_for_generic_english_title() -> None:
    instruction = (
        'Write an academic paper about blockchain and rural socialized services. '
        'Include one FIGURE block with caption kind data json fields.'
    )
    query = runtime_module._derive_reference_query(
        analysis={
            'topic': 'figure caption kind data json',
            'keywords': ['figure', 'caption', 'kind', 'data', 'json'],
        },
        analysis_summary='',
        instruction=instruction,
    )
    lowered = query.lower()
    assert 'academic' not in lowered
    assert 'paper' not in lowered
    assert 'figure' not in lowered
    assert 'caption' not in lowered
    assert 'kind' not in lowered
    assert 'data' not in lowered
    assert 'json' not in lowered
    assert 'blockchain' in lowered
    assert 'rural' in lowered


def test_normalize_reference_query_drops_schema_only_payload() -> None:
    query = runtime_module.graph_reference_domain.normalize_reference_query(
        '[[FIGURE:{"caption":"方法流程图","kind":"flow","data":{"nodes":[]}}]] figure caption kind data json'
    )
    assert query == ''
