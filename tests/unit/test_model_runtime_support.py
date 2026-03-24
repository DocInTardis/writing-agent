from __future__ import annotations

import json
import time
from types import SimpleNamespace

from writing_agent.web.model_runtime_support import (
    ensure_ollama_ready,
    ensure_ollama_ready_iter,
    pull_model_stream,
    pull_model_stream_iter,
    recommended_stream_timeouts,
    run_with_heartbeat,
)


def _drain(iterator):
    items: list[object] = []
    try:
        while True:
            items.append(next(iterator))
    except StopIteration as exc:
        return items, exc.value


class _Request:
    def __init__(self, *, url, data, headers, method):
        self.url = url
        self.data = data
        self.headers = headers
        self.method = method


class _Response:
    def __init__(self, lines):
        self._lines = lines

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def __iter__(self):
        return iter(self._lines)


def test_recommended_stream_timeouts_uses_metrics_and_probe_bounds() -> None:
    overall_s, stall_s = recommended_stream_timeouts(
        load_stream_metrics_fn=lambda: {
            'runs': [
                {'total_s': 100, 'max_gap_s': 10},
                {'total_s': 200, 'max_gap_s': 20},
            ]
        },
        percentile_fn=lambda values, _percentile: max(values) if values else 0.0,
        load_probe_fn=lambda: {'max_total_ms': 900_000, 'max_gap_ms': 120_000},
    )

    assert overall_s == 1080.0
    assert stall_s == 360.0


def test_run_with_heartbeat_emits_heartbeat_before_success() -> None:
    def _slow() -> str:
        time.sleep(1.1)
        return 'done'

    notes, result = _drain(
        run_with_heartbeat(_slow, 3.0, 'fallback', label='analysis', heartbeat_s=0.1)
    )

    assert notes == ['analysis...']
    assert result == 'done'


def test_run_with_heartbeat_returns_fallback_after_timeout() -> None:
    def _slow() -> str:
        time.sleep(2.2)
        return 'done'

    notes, result = _drain(
        run_with_heartbeat(_slow, 1.1, 'fallback', label='analysis', heartbeat_s=0.1)
    )

    assert notes == ['analysis...']
    assert result == 'fallback'


def test_pull_model_stream_iter_parses_progress_and_success() -> None:
    seen: dict[str, object] = {}

    def _urlopen(request, timeout):
        seen['request'] = request
        seen['timeout'] = timeout
        return _Response(
            [
                b'{"status":"pulling manifest"}\n',
                b'{"status":"downloading","completed":50,"total":100}\n',
                b'{"status":"success"}\n',
            ]
        )

    notes, result = _drain(
        pull_model_stream_iter(
            base_url='http://127.0.0.1:11434',
            name='tiny',
            timeout_s=3.0,
            url_request_cls=_Request,
            urlopen_fn=_urlopen,
        )
    )

    request = seen['request']
    assert request.url == 'http://127.0.0.1:11434/api/pull'
    assert json.loads(request.data.decode('utf-8')) == {'name': 'tiny', 'stream': True}
    assert request.headers == {'Content-Type': 'application/json'}
    assert request.method == 'POST'
    assert seen['timeout'] == 3.0
    assert notes == ['tiny: pulling manifest', 'tiny: downloading 50%', 'tiny: success']
    assert result == (True, '')



def test_pull_model_stream_passthrough_tuple_result() -> None:
    result = pull_model_stream(
        base_url='http://127.0.0.1:11434',
        name='tiny',
        timeout_s=3.0,
        pull_model_stream_iter_fn=lambda **_kwargs: (False, 'pull failed'),
    )

    assert result == (False, 'pull failed')



def test_ensure_ollama_ready_returns_success_when_service_running() -> None:
    settings = SimpleNamespace(
        enabled=True,
        base_url='http://127.0.0.1:11434',
        model='qwen2.5',
        timeout_s=30.0,
    )
    starts: list[str] = []
    captured: dict[str, object] = {}

    class _Client:
        def __init__(self, *, base_url, model, timeout_s):
            captured.update(base_url=base_url, model=model, timeout_s=timeout_s)

        def is_running(self) -> bool:
            return True

    result = ensure_ollama_ready(
        get_ollama_settings_fn=lambda: settings,
        ollama_client_cls=_Client,
        start_ollama_serve_fn=lambda: starts.append('started'),
        wait_until_fn=lambda predicate, timeout_s: predicate(),
    )

    assert result == (True, '')
    assert starts == []
    assert captured == {
        'base_url': 'http://127.0.0.1:11434',
        'model': 'qwen2.5',
        'timeout_s': 5.0,
    }



def test_ensure_ollama_ready_iter_starts_service_and_emits_note() -> None:
    state = {'running': False}
    settings = SimpleNamespace(
        enabled=True,
        base_url='http://127.0.0.1:11434',
        model='qwen2.5',
        timeout_s=30.0,
    )
    wait_calls: list[float] = []

    class _Client:
        def __init__(self, *, base_url, model, timeout_s):
            assert base_url == 'http://127.0.0.1:11434'
            assert model == 'qwen2.5'
            assert timeout_s == 5.0

        def is_running(self) -> bool:
            return state['running']

    def _start() -> None:
        state['running'] = True

    def _wait_until(predicate, timeout_s):
        wait_calls.append(timeout_s)
        return predicate()

    notes, result = _drain(
        ensure_ollama_ready_iter(
            get_ollama_settings_fn=lambda: settings,
            ollama_client_cls=_Client,
            start_ollama_serve_fn=_start,
            wait_until_fn=_wait_until,
        )
    )

    assert notes == ['checking model service: http://127.0.0.1:11434']
    assert result == (True, '')
    assert wait_calls == [12]
