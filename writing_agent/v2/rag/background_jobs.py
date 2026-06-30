"""Small daemon-backed scheduler for non-critical RAG enrichment."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

logger = logging.getLogger(__name__)

_RUNNING: set[str] = set()
_LOCK = threading.Lock()
_GROUP_LOCKS: dict[str, threading.Lock] = {}


def schedule_once(key: str, task: Callable[[], object], *, group: str = "") -> bool:
    job_key = str(key or "").strip()
    if not job_key:
        return False
    with _LOCK:
        if job_key in _RUNNING:
            return False
        _RUNNING.add(job_key)

    def _run() -> None:
        try:
            if group:
                with _group_lock(group):
                    task()
            else:
                task()
        except Exception:
            logger.warning("Background RAG task failed: %s", job_key, exc_info=True)
        finally:
            with _LOCK:
                _RUNNING.discard(job_key)

    thread = threading.Thread(target=_run, name=f"rag-{job_key[:40]}", daemon=True)
    thread.start()
    return True


def _group_lock(group: str) -> threading.Lock:
    with _LOCK:
        lock = _GROUP_LOCKS.get(group)
        if lock is None:
            lock = threading.Lock()
            _GROUP_LOCKS[group] = lock
        return lock
