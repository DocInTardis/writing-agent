from writing_agent.state_engine import (
    DocLockManager,
    StateContext,
    StateRuntime,
    classify_intent,
    classify_role,
    resolve_scope,
    route_execute_branch,
    run_cleanup,
)


class _Session:
    template_outline = []
    template_required_h2 = []


def test_lock_manager_global_and_partial_conflict():
    mgr = DocLockManager()
    ok, reason = mgr.acquire_partial("doc1", "u1", scope_type="block", target_ids=["b1"])
    assert ok and reason is None

    status, reason = mgr.resolve_conflict("doc1", "u2", ["b2"])
    assert status == "success"
    ok, reason = mgr.acquire_partial("doc1", "u2", scope_type="block", target_ids=["b2"])
    assert ok and reason is None

    ok, reason = mgr.acquire_partial("doc1", "u3", scope_type="block", target_ids=["b1"])
    assert not ok
    assert reason

    ok, reason = mgr.acquire_global("doc1", "u4")
    assert not ok
    assert reason

    mgr.release_owner("doc1", "u1")
    mgr.release_owner("doc1", "u2")
    ok, reason = mgr.acquire_global("doc1", "u4")
    assert ok and reason is None


def test_cleanup_unlock_first_even_if_followup_fails():
    ctx = StateContext.create(
        session_id="s1",
        doc_id="d1",
        request_source="chat",
        instruction_raw="x",
        instruction_normalized="x",
    )
    order: list[str] = []

    def _release() -> None:
        order.append("release")

    def _temp() -> None:
        order.append("temp")
        raise RuntimeError("temp fail")

    def _log() -> None:
        order.append("log")

    run_cleanup(
        ctx,
        release_locks=_release,
        clean_temp_files=_temp,
        flush_logs=_log,
    )
    assert order[0] == "release"
    assert ctx.cleanup.lock_release_done is True
    assert ctx.locks.released is True
    assert ctx.error.code == "CLEANUP_PARTIAL_FAILED"


def test_routing_decision_for_format_and_block_revise():
    role, role_conf = classify_role(_Session(), "请修改这段")
    assert role == "R04"
    assert role_conf > 0
    intent, _ = classify_intent("把字体改成宋体", has_format_only=True)
    assert intent == "I06"
    scope = resolve_scope(selection="", block_ids=["b1"], section="")
    assert scope == "C04"
    d = route_execute_branch(role, "I04", scope)
    assert d.route == "E05"


def test_runtime_transition_records_event():
    ctx = StateContext.create(
        session_id="s1",
        doc_id="d1",
        request_source="chat",
        instruction_raw="x",
        instruction_normalized="x",
    )
    rt = StateRuntime(ctx)
    ev = rt.transition(
        to_state="G07_GUARD_PASS",
        trigger="INTENT_RESOLVED",
        guard="route_resolved",
        action="route:E05",
    )
    assert ev.from_state == "S02_DOC_READY"
    assert ev.to_state == "G07_GUARD_PASS"
    assert ctx.state == "G07_GUARD_PASS"
    assert len(rt.events) == 1

