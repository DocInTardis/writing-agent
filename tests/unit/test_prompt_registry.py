from pathlib import Path

from writing_agent.v2.prompt_registry import PromptRegistry, fallback_prompt_payload, prompt_schema_valid


def test_prompt_schema_valid_true() -> None:
    assert prompt_schema_valid(fallback_prompt_payload()) is True


def test_prompt_registry_choose_ab_is_stable() -> None:
    reg = PromptRegistry(path=".data/out/test_prompt_registry.json")
    arm1 = reg.choose_ab("writer", user_key="u-1", ratio_a=0.5)
    arm2 = reg.choose_ab("writer", user_key="u-1", ratio_a=0.5)
    assert arm1 in {"A", "B"}
    assert arm1 == arm2


def test_prompt_registry_register_and_get_active(tmp_path: Path) -> None:
    path = tmp_path / "prompts.json"
    reg = PromptRegistry(path=path)
    reg.register_variant(
        prompt_id="writer.academic_cn",
        version="2026.03.07-v1",
        payload={"temperature": 0.2},
        owner="qa",
        tags=["writer", "zh"],
        changelog="init",
    )
    active = reg.get_active("writer.academic_cn")
    assert active is not None
    assert active.owner == "qa"
    assert active.status == "active"
    assert "writer" in set(active.tags)
    assert active.payload.get("temperature") == 0.2


def test_prompt_registry_rollback_disables_non_target(tmp_path: Path) -> None:
    path = tmp_path / "prompts.json"
    reg = PromptRegistry(path=path)
    reg.register_variant(prompt_id="planner.academic_cn", version="v1", payload={"temperature": 0.2})
    reg.register_variant(prompt_id="planner.academic_cn", version="v2", payload={"temperature": 0.3})
    ok = reg.rollback("planner.academic_cn", "v1")
    assert ok is True
    active = reg.get_active("planner.academic_cn")
    assert active is not None
    assert active.version == "v1"


def test_prompt_registry_circuit_breaker_checks_thresholds(tmp_path: Path) -> None:
    reg = PromptRegistry(path=tmp_path / "prompts.json")
    trip, reasons = reg.should_trip_circuit(
        {
            "failure_rate": 0.31,
            "zh_rate": 0.7,
            "structure_rate": 0.9,
            "citation_rate": 0.7,
        }
    )
    assert trip is True
    assert "failure_rate" in reasons
    assert "zh_rate" in reasons
    assert "citation_rate" in reasons
