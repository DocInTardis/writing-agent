from writing_agent.web.api.editing_flow import (
    _normalize_inline_context_policy,
    _trim_inline_context,
)


def test_inline_context_policy_trims_large_side_contexts():
    policy = _normalize_inline_context_policy(None)
    before = "L" * 5000
    after = "R" * 5000
    left, right, meta = _trim_inline_context(
        selected_text="old",
        before_text=before,
        after_text=after,
        policy=policy,
    )
    assert len(left) <= 1200
    assert len(right) <= 1200
    assert len(left) > 0
    assert len(right) > 0
    assert meta["trimmed_for_budget"] is True
    assert meta["policy_version"] == "dynamic_v1"


def test_inline_context_policy_honors_custom_window_bounds():
    policy = _normalize_inline_context_policy(
        {
            "window_min_chars": 300,
            "window_max_chars": 300,
            "context_total_max_chars": 600,
        }
    )
    before = "A" * 2000
    after = "B" * 2000
    left, right, meta = _trim_inline_context(
        selected_text="target text",
        before_text=before,
        after_text=after,
        policy=policy,
    )
    assert len(left) == 300
    assert len(right) == 300
    assert meta["left_window_chars"] == 300
    assert meta["right_window_chars"] == 300
