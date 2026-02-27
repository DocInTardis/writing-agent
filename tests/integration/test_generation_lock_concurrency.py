import threading

from writing_agent.web.generation_lock import DocGenerationState


def test_generation_lock_concurrency() -> None:
    state = DocGenerationState(stale_after_s=10.0, max_age_s=10.0)
    results: list[str | None] = []

    def worker() -> None:
        token = state.try_begin('doc-1', mode='generate')
        results.append(token)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    acquired = [x for x in results if x]
    assert len(acquired) == 1
