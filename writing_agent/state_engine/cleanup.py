"""Cleanup module.

This module belongs to `writing_agent.state_engine` in the writing-agent codebase.
"""

from __future__ import annotations

from typing import Callable

from .context import StateContext


def run_cleanup(
    context: StateContext,
    *,
    release_locks: Callable[[], None],
    clean_temp_files: Callable[[], None] | None = None,
    flush_logs: Callable[[], None] | None = None,
) -> None:
    # Always unlock first so the editor can recover immediately.
    try:
        release_locks()
        context.cleanup.lock_release_done = True
        context.locks.released = True
    except Exception as exc:
        context.error.code = "CLEANUP_PARTIAL_FAILED"
        context.error.message = f"release locks failed: {exc}"
        context.error.retryable = True
        context.cleanup.lock_release_done = False
        context.locks.released = False
        return

    if clean_temp_files is not None:
        try:
            clean_temp_files()
            context.cleanup.temp_clean_done = True
        except Exception as exc:
            context.error.code = "CLEANUP_PARTIAL_FAILED"
            context.error.message = f"temp cleanup failed: {exc}"
            context.error.retryable = True

    if flush_logs is not None:
        try:
            flush_logs()
            context.cleanup.log_flush_done = True
        except Exception as exc:
            context.error.code = "CLEANUP_PARTIAL_FAILED"
            context.error.message = f"log flush failed: {exc}"
            context.error.retryable = True

