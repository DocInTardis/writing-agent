from writing_agent.web.domains import context_policy_domain


def test_inline_policy_accepts_short_boost_alias():
    policy = context_policy_domain.normalize_inline_context_policy(
        {
            "short_boost_chars": 321,
            "window_min_chars": 200,
            "window_max_chars": 200,
        }
    )
    assert int(policy.get("short_selection_extra_chars") or 0) == 321
    assert int(policy.get("window_min_chars") or 0) == 200
    assert int(policy.get("window_max_chars") or 0) == 200


def test_revision_policy_accepts_short_selection_extra_alias():
    policy = context_policy_domain.normalize_selected_revision_context_policy(
        {
            "short_selection_extra_chars": 345,
        }
    )
    assert int(policy.get("short_boost_chars") or 0) == 345


def test_policy_defaults_can_be_overridden_by_env_json(monkeypatch):
    monkeypatch.setenv(
        "WRITING_AGENT_CONTEXT_POLICY_REVISION_DEFAULTS_JSON",
        '{"window_min_chars": 333, "window_max_chars": 333, "prompt_budget_ratio": 0.22}',
    )
    policy = context_policy_domain.normalize_selected_revision_context_policy(None)
    assert int(policy.get("window_min_chars") or 0) == 333
    assert int(policy.get("window_max_chars") or 0) == 333
    assert abs(float(policy.get("prompt_budget_ratio") or 0.0) - 0.22) < 1e-9


def test_revision_prompt_context_tokens_uses_backend_env(monkeypatch):
    monkeypatch.setenv("WRITING_AGENT_CONTEXT_PROMPT_TOKENS", "4096")
    policy = context_policy_domain.normalize_selected_revision_context_policy({})
    assert int(policy.get("prompt_context_tokens") or 0) == 4096

