from __future__ import annotations

import threading
import time

from writing_agent.web.generation_lock import DocGenerationState


class _Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def now(self) -> float:
        return self.t

    def step(self, seconds: float) -> None:
        self.t += float(seconds)


def test_lock_expires_after_idle_window():
    clock = _Clock()
    lock = DocGenerationState(stale_after_s=10, max_age_s=0, time_fn=clock.now)

    token1 = lock.try_begin("doc-1", mode="stream")
    assert token1
    assert lock.try_begin("doc-1", mode="stream") is None

    clock.step(11)
    token2 = lock.try_begin("doc-1", mode="stream")
    assert token2 and token2 != token1


def test_touch_prevents_idle_expiration_until_window_exceeded():
    clock = _Clock()
    lock = DocGenerationState(stale_after_s=10, max_age_s=0, time_fn=clock.now)

    token = lock.try_begin("doc-2", mode="stream")
    assert token

    clock.step(9)
    assert lock.touch("doc-2", token) is True
    clock.step(6)
    assert lock.try_begin("doc-2", mode="stream") is None

    clock.step(5)
    token2 = lock.try_begin("doc-2", mode="stream")
    assert token2 and token2 != token


def test_is_busy_clears_expired_state():
    clock = _Clock()
    lock = DocGenerationState(stale_after_s=5, max_age_s=0, time_fn=clock.now)

    token = lock.try_begin("doc-3", mode="generate")
    assert token
    assert lock.is_busy("doc-3") is True

    clock.step(6)
    assert lock.is_busy("doc-3") is False
    assert lock.try_begin("doc-3", mode="generate")


def test_begin_with_wait_can_acquire_after_previous_finish():
    lock = DocGenerationState(stale_after_s=60, max_age_s=120)
    token = lock.try_begin("doc-4", mode="stream")
    assert token

    def _release_later() -> None:
        time.sleep(0.08)
        lock.finish("doc-4", token)

    t = threading.Thread(target=_release_later, daemon=True)
    t.start()
    token2 = lock.begin_with_wait("doc-4", mode="stream", wait_s=0.6, poll_s=0.02)
    t.join(timeout=1.0)

    assert token2
    assert token2 != token


def test_begin_with_wait_returns_none_on_timeout():
    lock = DocGenerationState(stale_after_s=60, max_age_s=120)
    token = lock.try_begin("doc-5", mode="generate")
    assert token
    token2 = lock.begin_with_wait("doc-5", mode="generate", wait_s=0.05, poll_s=0.01)
    assert token2 is None
