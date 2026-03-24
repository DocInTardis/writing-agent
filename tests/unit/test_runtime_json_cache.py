from __future__ import annotations

import threading

from writing_agent.v2 import graph_runner_runtime as runtime_module


def test_runtime_json_cache_roundtrip(tmp_path):
    cache = runtime_module.LocalCache(tmp_path / "cache")
    key = runtime_module._runtime_json_cache_key(cache, "analysis_v1", "openai", "gpt-5.4", "instr")
    payload = {"topic": "区块链", "keywords": ["区块链", "CiteSpace"]}

    runtime_module._runtime_json_cache_put(cache, key, payload, metadata={"type": "analysis"})
    cached = runtime_module._runtime_json_cache_get(cache, key)

    assert cached == payload


def test_plan_map_serialize_roundtrip():
    plan = {
        "引言": runtime_module.PlanSection(
            title="引言",
            target_chars=800,
            min_chars=500,
            max_chars=1000,
            min_tables=0,
            min_figures=0,
            key_points=["背景", "问题"],
            figures=[{"caption": "图1"}],
            tables=[{"caption": "表1"}],
            evidence_queries=["区块链 农村社会化服务"],
        )
    }

    serialized = runtime_module._serialize_plan_map(plan)
    restored = runtime_module._deserialize_plan_map(serialized)

    assert list(restored.keys()) == ["引言"]
    assert restored["引言"].title == "引言"
    assert restored["引言"].key_points == ["背景", "问题"]
    assert restored["引言"].evidence_queries == ["区块链 农村社会化服务"]



def test_runtime_json_cache_enabled_accepts_legacy_env(monkeypatch):
    monkeypatch.delenv("WRITING_AGENT_RUNTIME_JSON_CACHE", raising=False)
    monkeypatch.setenv("WRITING_AGENT_ENABLE_RUNTIME_JSON_CACHE", "0")
    assert runtime_module._runtime_json_cache_enabled() is False

    monkeypatch.setenv("WRITING_AGENT_ENABLE_RUNTIME_JSON_CACHE", "1")
    assert runtime_module._runtime_json_cache_enabled() is True



def test_load_evidence_pack_cached_roundtrip(tmp_path, monkeypatch):
    cache = runtime_module.LocalCache(tmp_path / "cache")
    cache_lock = threading.Lock()
    calls: list[str] = []
    plan = runtime_module.PlanSection(
        title="??",
        target_chars=800,
        min_chars=500,
        max_chars=1000,
        min_tables=0,
        min_figures=0,
        key_points=["??"],
        figures=[],
        tables=[],
        evidence_queries=["???"],
    )

    def _fake_build_evidence_pack(**kwargs):
        calls.append(str(kwargs.get("section") or ""))
        return {
            "summary": "evidence summary",
            "sources": [{"title": "A"}],
            "allowed_urls": ["https://example.test/a"],
            "data_starvation": {"is_starved": False, "stub_mode": False},
            "facts": [{"claim": "A"}],
            "fact_gain_count": 1,
            "fact_density_score": 0.5,
            "online_hits": 2,
        }

    monkeypatch.setenv("WRITING_AGENT_RUNTIME_JSON_CACHE", "1")
    monkeypatch.setattr(runtime_module, "_build_evidence_pack", _fake_build_evidence_pack)

    payload1, cache_hit1 = runtime_module._load_evidence_pack_cached(
        local_cache=cache,
        cache_lock=cache_lock,
        provider_name="openai",
        model="gpt-5.4",
        instruction="????",
        section="??",
        analysis={"topic": "???"},
        plan=plan,
        base_url="https://example.test/v1",
    )
    payload2, cache_hit2 = runtime_module._load_evidence_pack_cached(
        local_cache=cache,
        cache_lock=cache_lock,
        provider_name="openai",
        model="gpt-5.4",
        instruction="????",
        section="??",
        analysis={"topic": "???"},
        plan=plan,
        base_url="https://example.test/v1",
    )

    assert cache_hit1 is False
    assert cache_hit2 is True
    assert calls == ["??"]
    assert payload1["summary"] == "evidence summary"
    assert payload2["allowed_urls"] == ["https://example.test/a"]
    assert payload2["fact_gain_count"] == 1



def test_prime_cached_sections_skips_reference(tmp_path):
    cache = runtime_module.LocalCache(tmp_path / "cache")
    cache_lock = threading.Lock()
    targets = {
        "??": runtime_module.SectionTargets(weight=1.0, min_paras=2, min_chars=500, max_chars=0, min_tables=0, min_figures=0),
        "????": runtime_module.SectionTargets(weight=1.0, min_paras=1, min_chars=100, max_chars=0, min_tables=0, min_figures=0),
    }
    cache.put_section("??", "????", 500, "???????????" * 20)
    cache.put_section("????", "????", 100, "[1] Test reference")

    hits = runtime_module._prime_cached_sections(
        sections=["??", "????"],
        targets=targets,
        instruction="????",
        local_cache=cache,
        cache_lock=cache_lock,
    )

    assert "??" in hits
    assert "????" not in hits



def test_prime_cached_sections_repairs_keyword_escape_residue(tmp_path):
    cache = runtime_module.LocalCache(tmp_path / "cache")
    cache_lock = threading.Lock()
    section = "\u5173\u952e\u8bcd"
    instruction = "\u533a\u5757\u94fe\u4e0e\u519c\u6751\u793e\u4f1a\u5316\u670d\u52a1"
    targets = {
        section: runtime_module.SectionTargets(
            weight=1.0,
            min_paras=1,
            min_chars=0,
            max_chars=0,
            min_tables=0,
            min_figures=0,
        )
    }
    corrupted = "\u5173\u952e\u8bcd\uff1a" + r"\xe5\x8c\xba\xe5\x9d\x97\xe9\x93\xbe" + "\uff1b[1]\uff1bCiteSpace\uff1b\u519c\u6751\u793e\u4f1a\u5316\u670d\u52a1"
    cache.put_section(section, instruction, 0, corrupted)

    hits = runtime_module._prime_cached_sections(
        sections=[section],
        targets=targets,
        instruction=instruction,
        local_cache=cache,
        cache_lock=cache_lock,
    )

    assert section in hits
    assert r"\x" not in hits[section]
    assert "[1]" not in hits[section]
    assert "\u533a\u5757\u94fe" in hits[section]
