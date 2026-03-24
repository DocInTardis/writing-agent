from writing_agent.capabilities.editing import trim_inline_context


def test_trim_inline_context_enforces_window_and_budget() -> None:
    left, right, meta = trim_inline_context(
        selected_text="old",
        before_text="L" * 5000,
        after_text="R" * 5000,
        policy={"version": "test_v1"},
    )

    assert len(left) <= 1200
    assert len(right) <= 1200
    assert meta["policy_version"] == "test_v1"
    assert meta["trimmed_for_budget"] is True


def test_trim_inline_context_honors_custom_window_bounds() -> None:
    left, right, meta = trim_inline_context(
        selected_text="target text",
        before_text="A" * 2000,
        after_text="B" * 2000,
        policy={
            "window_min_chars": 300,
            "window_max_chars": 300,
            "context_total_max_chars": 600,
        },
    )

    assert len(left) == 300
    assert len(right) == 300
    assert meta["left_window_chars"] == 300
    assert meta["right_window_chars"] == 300
