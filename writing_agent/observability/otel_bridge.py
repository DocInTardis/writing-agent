"""Otel Bridge module.

This module belongs to `writing_agent.observability` in the writing-agent codebase.
"""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator


@dataclass
class OTelBridge:
    enabled: bool = False

    @contextmanager
    def span(self, name: str, *, correlation_id: str = "") -> Iterator[dict]:
        start = time.time()
        payload = {
            "name": str(name or ""),
            "correlation_id": str(correlation_id or ""),
            "start": start,
        }
        try:
            yield payload
        finally:
            payload["end"] = time.time()
            payload["duration_ms"] = int((payload["end"] - start) * 1000)


def get_bridge() -> OTelBridge:
    raw = str(os.environ.get("WRITING_AGENT_OTEL_ENABLED", "0")).strip().lower()
    enabled = raw in {"1", "true", "yes", "on"}
    if not enabled:
        return OTelBridge(enabled=False)
    # Optional dependency use; fallback gracefully.
    try:
        import opentelemetry  # noqa: F401

        return OTelBridge(enabled=True)
    except Exception:
        return OTelBridge(enabled=False)
