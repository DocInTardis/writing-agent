from writing_agent.state_engine.dual_engine import DualGraphEngine


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
