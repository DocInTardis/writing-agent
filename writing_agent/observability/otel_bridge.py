"""Otel Bridge module.

This module belongs to `writing_agent.observability` in the writing-agent codebase.
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator

logger = logging.getLogger(__name__)


@dataclass
class OTelBridge:
    enabled: bool = False
    _tracer: Any = field(default=None, repr=False)

    @contextmanager
    def span(self, name: str, *, correlation_id: str = "") -> Iterator[dict]:
        start = time.time()
        payload = {
            "name": str(name or ""),
            "correlation_id": str(correlation_id or ""),
            "start": start,
        }
        otel_span = None
        if self.enabled and self._tracer is not None:
            try:
                otel_span = self._tracer.start_as_current_span(str(name or ""))
                if otel_span is not None:
                    otel_span.__enter__()
                    if correlation_id:
                        otel_span.set_attribute("correlation_id", str(correlation_id))
            except Exception as _exc:
                logger.debug("OTel span start failed: %s", _exc, exc_info=True)
                otel_span = None
        try:
            yield payload
        finally:
            payload["end"] = time.time()
            payload["duration_ms"] = int((payload["end"] - start) * 1000)
            if otel_span is not None:
                try:
                    otel_span.__exit__(None, None, None)
                except Exception as _exc:
                    logger.debug("OTel span end failed: %s", _exc, exc_info=True)


def get_bridge() -> OTelBridge:
    raw = str(os.environ.get("WRITING_AGENT_OTEL_ENABLED", "0")).strip().lower()
    enabled = raw in {"1", "true", "yes", "on"}
    if not enabled:
        return OTelBridge(enabled=False)
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

        provider = TracerProvider()
        otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
        exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        tracer = trace.get_tracer("writing-agent")
        return OTelBridge(enabled=True, _tracer=tracer)
    except Exception as _exc:
        logger.debug("OTel initialization failed, falling back to no-op: %s", _exc, exc_info=True)
        return OTelBridge(enabled=False)
