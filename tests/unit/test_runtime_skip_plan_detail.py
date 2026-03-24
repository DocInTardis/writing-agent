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
    monkeypatch.setenv("WRITING_AGENT_FAST_PLAN", "0")
    monkeypatch.setenv("WRITING_AGENT_FAST_DRAFT", "1")
    monkeypatch.setenv("WRITING_AGENT_STRICT_JSON", "0")
    monkeypatch.setenv("WRITING_AGENT_MIN_H2_COUNT", "1")
    monkeypatch.setenv("WRITING_AGENT_MIN_REFERENCE_ITEMS", "0")
    monkeypatch.setenv("WRITING_AGENT_ENFORCE_REFERENCE_MIN", "0")
    monkeypatch.setenv("WRITING_AGENT_ENFORCE_FINAL_VALIDATION", "0")
    monkeypatch.setenv("WRITING_AGENT_ENFORCE_META_FIREWALL", "0")
    monkeypatch.setenv("WRITING_AGENT_ENFORCE_CONTRACT_SLOTS", "0")
    monkeypatch.setenv("WRITING_AGENT_EVIDENCE_ENABLED", "0")
    monkeypatch.setenv("WRITING_AGENT_RAG_THEME_GATE_ENABLED", "0")
    monkeypatch.setenv("WRITING_AGENT_FORCE_REQUIRED_OUTLINE_ONLY", "1")
    monkeypatch.setenv("WRITING_AGENT_REQUIRED_OUTLINE_ONLY", "1")


def test_runtime_can_skip_plan_detail_via_env(monkeypatch):
    _patch_runtime_common(monkeypatch)
    monkeypatch.setenv("WRITING_AGENT_SKIP_PLAN_DETAIL", "1")
    monkeypatch.setenv("WRITING_AGENT_ALLOW_SKIP_PLAN_DETAIL", "1")
    monkeypatch.setattr(runtime_module, "_plan_sections_with_model", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("plan detail should be skipped")))
    monkeypatch.setattr(
        runtime_module,
        "_fast_fill_section",
        lambda section, **_kwargs: (
            "Blockchain improves traceability and service coordination in rural service systems."
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
            config=GenerateConfig(workers=1, min_total_chars=400),
        )
    )

    skip_events = [ev for ev in events if isinstance(ev, dict) and str(ev.get("event") or "") == "plan_detail_skipped"]
    assert skip_events
    final = [ev for ev in events if isinstance(ev, dict) and str(ev.get("event") or "") == "final"][-1]
    assert str(final.get("runtime_status") or "") == "success"



def test_runtime_ignores_skip_plan_detail_without_dev_allowance(monkeypatch):
    _patch_runtime_common(monkeypatch)
    monkeypatch.setenv("WRITING_AGENT_SKIP_PLAN_DETAIL", "1")
    monkeypatch.delenv("WRITING_AGENT_ALLOW_SKIP_PLAN_DETAIL", raising=False)
    planned = {"called": False}

    def _fake_plan(**_kwargs):
        planned["called"] = True
        return {
            "Introduction": runtime_module.PlanSection(
                title="Introduction",
                target_chars=400,
                min_chars=240,
                max_chars=800,
                min_tables=0,
                min_figures=0,
                key_points=["background", "problem"],
                figures=[],
                tables=[],
                evidence_queries=["blockchain rural services research"],
            ),
            "References": runtime_module.PlanSection(
                title="References",
                target_chars=200,
                min_chars=120,
                max_chars=500,
                min_tables=0,
                min_figures=0,
                key_points=[],
                figures=[],
                tables=[],
                evidence_queries=[],
            ),
        }

    monkeypatch.setattr(runtime_module, "_plan_sections_with_model", _fake_plan)
    monkeypatch.setattr(
        runtime_module,
        "_fast_fill_section",
        lambda section, **_kwargs: (
            "Blockchain improves traceability and service coordination in rural service systems."
            if "References" not in str(section)
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
            config=GenerateConfig(workers=1, min_total_chars=400),
        )
    )

    ignored = [ev for ev in events if isinstance(ev, dict) and str(ev.get("event") or "") == "plan_detail_skip_ignored"]
    assert ignored
    assert planned["called"] is True



def test_runtime_force_required_outline_only_locks_struct_plan_to_required_sections(monkeypatch):
    _patch_runtime_common(monkeypatch)
    monkeypatch.setenv("WRITING_AGENT_SKIP_PLAN_DETAIL", "1")
    monkeypatch.setenv("WRITING_AGENT_ALLOW_SKIP_PLAN_DETAIL", "1")
    monkeypatch.setattr(
        runtime_module,
        "_analyze_instruction",
        lambda **_kwargs: {
            "topic": "blockchain rural services",
            "doc_type": "academic",
            "audience": "researcher",
            "style": "formal",
            "keywords": ["blockchain", "rural services"],
            "must_include": ["Introduction", "Related Work", "Data Source and Retrieval Strategy", "Conclusion"],
            "constraints": [],
            "_confidence_score": 0.98,
            "_schema_valid": True,
            "_needs_clarification": False,
        },
    )
    monkeypatch.setattr(
        runtime_module,
        "_fast_fill_section",
        lambda section, **_kwargs: (
            "Core content for " + str(section)
            if "References" not in str(section)
            else ""
        ),
    )

    events = list(
        runtime_module.run_generate_graph(
            instruction="Write an academic paper about blockchain and rural socialized services.",
            current_text="",
            required_h2=["Introduction", "System Architecture", "Conclusion", "References"],
            required_outline=[
                (2, "Introduction"),
                (2, "System Architecture"),
                (2, "Conclusion"),
                (2, "References"),
            ],
            expand_outline=False,
            config=GenerateConfig(workers=1, min_total_chars=400),
        )
    )

    lock_events = [ev for ev in events if isinstance(ev, dict) and str(ev.get("event") or "") == "required_outline_lock"]
    assert lock_events
    assert list(lock_events[-1].get("sections") or []) == [
        "Introduction",
        "System Architecture",
        "Conclusion",
        "\u53c2\u8003\u6587\u732e",
    ]

    struct_plan_events = [ev for ev in events if isinstance(ev, dict) and str(ev.get("event") or "") == "struct_plan"]
    assert struct_plan_events
    plan_titles = [str(row.get("title") or "") for row in list((struct_plan_events[-1].get("plan") or {}).get("sections") or [])]
    assert plan_titles == ["Introduction", "System Architecture", "Conclusion", "\u53c2\u8003\u6587\u732e"]

    final = [ev for ev in events if isinstance(ev, dict) and str(ev.get("event") or "") == "final"][-1]
    final_text = str(final.get("text") or "")
    assert "## Related Work" not in final_text
    assert "## Data Source and Retrieval Strategy" not in final_text
