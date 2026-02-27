from writing_agent.v2.prompt_registry import PromptRegistry, fallback_prompt_payload, prompt_schema_valid


def test_prompt_schema_valid_true() -> None:
    assert prompt_schema_valid(fallback_prompt_payload()) is True


def test_prompt_registry_choose_ab_is_stable() -> None:
    reg = PromptRegistry(path='.data/out/test_prompt_registry.json')
    arm1 = reg.choose_ab('writer', user_key='u-1', ratio_a=0.5)
    arm2 = reg.choose_ab('writer', user_key='u-1', ratio_a=0.5)
    assert arm1 in {'A', 'B'}
    assert arm1 == arm2
