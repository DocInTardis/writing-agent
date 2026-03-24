from writing_agent.state_engine.dual_engine import DualGraphEngine, should_use_langgraph


def test_dual_engine_native_runs_and_returns_state() -> None:
    engine = DualGraphEngine(use_langgraph=False)
    handlers = {
        'planner': lambda s: {'plan': {'ok': True}, 'required_h2': [], 'required_outline': [], 'metadata': {}},
        'writer': lambda s: {'draft': 'hello world', 'section_events': [], 'metadata': {}},
        'reviewer': lambda s: {'review': {'issues': []}, 'fixups': [], 'metadata': {}},
        'qa': lambda s: {'final_text': s.get('draft', ''), 'problems': [], 'metadata': {}},
    }
    state, events = engine.run(
        run_id='unit-dual-engine',
        payload={
            'instruction': 'write',
            'current_text': '',
            'compose_mode': 'auto',
            'resume_sections': [],
            'format_only': False,
        },
        handlers=handlers,
    )
    assert state.get('final_text') == 'hello world'
    assert len(events) >= 4


def test_dual_engine_route_format_only_enters_qa_only() -> None:
    engine = DualGraphEngine(use_langgraph=False)
    calls: list[str] = []

    def _planner(s):
        calls.append('planner')
        return {'plan': {'ok': True}}

    def _writer(s):
        calls.append('writer')
        return {'draft': 'writer text'}

    def _reviewer(s):
        calls.append('reviewer')
        return {'review': {'issues': []}, 'fixups': []}

    def _qa(s):
        calls.append('qa')
        return {'final_text': str(s.get('draft') or ''), 'problems': list((s.get('review') or {}).get('issues') or [])}

    state, events = engine.run(
        run_id='unit-dual-engine-format-only',
        payload={
            'instruction': 'format only',
            'current_text': 'kept text',
            'compose_mode': 'auto',
            'resume_sections': [],
            'format_only': True,
        },
        handlers={
            'planner': _planner,
            'writer': _writer,
            'reviewer': _reviewer,
            'qa': _qa,
        },
    )

    assert calls == ['qa']
    assert state.get('final_text') == 'kept text'
    route = state.get('_route') if isinstance(state.get('_route'), dict) else {}
    assert route.get('id') == 'format_only'
    assert route.get('entry_node') == 'qa'
    assert len(events) == 1
    assert ((events[0].get('metadata') or {}).get('route_id')) == 'format_only'


def test_dual_engine_route_resume_sections_starts_from_writer() -> None:
    engine = DualGraphEngine(use_langgraph=False)
    calls: list[str] = []

    def _planner(s):
        calls.append('planner')
        return {'plan': {'from_planner': True}}

    def _writer(s):
        calls.append('writer')
        return {'draft': 'resumed text'}

    def _reviewer(s):
        calls.append('reviewer')
        return {'review': {'issues': []}, 'fixups': []}

    def _qa(s):
        calls.append('qa')
        return {'final_text': str(s.get('draft') or ''), 'problems': []}

    state, events = engine.run(
        run_id='unit-dual-engine-resume-sections',
        payload={
            'instruction': 'continue methods',
            'current_text': 'base text',
            'compose_mode': 'continue',
            'resume_sections': ['Methods'],
            'format_only': False,
        },
        handlers={
            'planner': _planner,
            'writer': _writer,
            'reviewer': _reviewer,
            'qa': _qa,
        },
    )

    assert calls == ['writer', 'reviewer', 'qa']
    route = state.get('_route') if isinstance(state.get('_route'), dict) else {}
    assert route.get('id') == 'resume_sections'
    assert route.get('entry_node') == 'writer'
    plan = state.get('plan') if isinstance(state.get('plan'), dict) else {}
    assert list(plan.get('resume_sections') or []) == ['Methods']
    assert ((events[0].get('metadata') or {}).get('route_id')) == 'resume_sections'


def test_dual_engine_route_compose_mode_runs_full_chain() -> None:
    engine = DualGraphEngine(use_langgraph=False)
    calls: list[str] = []

    def _planner(s):
        calls.append('planner')
        return {'plan': {'ok': True}, 'required_h2': [], 'required_outline': []}

    def _writer(s):
        calls.append('writer')
        return {'draft': 'full chain'}

    def _reviewer(s):
        calls.append('reviewer')
        return {'review': {'issues': []}, 'fixups': []}

    def _qa(s):
        calls.append('qa')
        return {'final_text': str(s.get('draft') or ''), 'problems': []}

    state, events = engine.run(
        run_id='unit-dual-engine-compose-mode',
        payload={
            'instruction': 'write',
            'current_text': '',
            'compose_mode': 'auto',
            'resume_sections': [],
            'format_only': False,
        },
        handlers={
            'planner': _planner,
            'writer': _writer,
            'reviewer': _reviewer,
            'qa': _qa,
        },
    )

    assert calls == ['planner', 'writer', 'reviewer', 'qa']
    route = state.get('_route') if isinstance(state.get('_route'), dict) else {}
    assert route.get('id') == 'compose_mode'
    assert route.get('entry_node') == 'planner'
    assert len(events) == 4


def test_dual_engine_resume_reuses_checkpoint_route() -> None:
    engine = DualGraphEngine(use_langgraph=False)

    handlers = {
        'planner': lambda s: {'plan': {'ok': True}, 'required_h2': [], 'required_outline': []},
        'writer': lambda s: {'draft': 'resumed route text'},
        'reviewer': lambda s: {'review': {'issues': []}, 'fixups': []},
        'qa': lambda s: {'final_text': str(s.get('draft') or ''), 'problems': []},
    }

    state1, _events1 = engine.run(
        run_id='unit-dual-engine-route-resume',
        payload={
            'instruction': 'continue writing',
            'current_text': 'base',
            'compose_mode': 'continue',
            'resume_sections': ['Intro'],
            'format_only': False,
        },
        handlers=handlers,
        resume=False,
    )
    route1 = state1.get('_route') if isinstance(state1.get('_route'), dict) else {}
    assert route1.get('id') == 'resume_sections'
    assert route1.get('entry_node') == 'writer'

    # Resume should continue from historical route metadata in checkpoint state.
    state2, _events2 = engine.run(
        run_id='unit-dual-engine-route-resume',
        payload={
            'instruction': 'format only now',
            'current_text': 'base',
            'compose_mode': 'auto',
            'resume_sections': [],
            'format_only': True,
        },
        handlers=handlers,
        resume=True,
    )
    route2 = state2.get('_route') if isinstance(state2.get('_route'), dict) else {}
    assert route2.get('id') == 'resume_sections'
    assert route2.get('entry_node') == 'writer'



def test_should_use_langgraph_defaults_to_auto_enabled(monkeypatch) -> None:
    monkeypatch.delenv("WRITING_AGENT_GRAPH_ENGINE", raising=False)
    assert should_use_langgraph() is True


def test_should_use_langgraph_explicit_native_disables_langgraph(monkeypatch) -> None:
    monkeypatch.setenv("WRITING_AGENT_GRAPH_ENGINE", "native")
    assert should_use_langgraph() is False


def test_dual_engine_langgraph_failure_falls_back_to_native(monkeypatch) -> None:
    engine = DualGraphEngine(use_langgraph=True)

    def _boom_langgraph(**_kwargs):
        raise RuntimeError("langgraph unavailable")

    def _native(**_kwargs):
        return ({"final_text": "native fallback"}, [{"metadata": {"engine": "native"}}])

    monkeypatch.setattr(engine, "_run_langgraph", _boom_langgraph)
    monkeypatch.setattr(engine, "_run_native", _native)

    state, events = engine.run(
        run_id='unit-dual-engine-langgraph-fallback',
        payload={
            'instruction': 'write',
            'current_text': '',
            'compose_mode': 'auto',
            'resume_sections': [],
            'format_only': False,
        },
        handlers={},
    )

    assert state.get('final_text') == 'native fallback'
    assert ((events[0].get('metadata') or {}).get('engine')) == 'native'
