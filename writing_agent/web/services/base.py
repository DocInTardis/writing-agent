"""Base module.

This module belongs to `writing_agent.web.services` in the writing-agent codebase.
"""

from __future__ import annotations

from typing import Any, Mapping


class ServiceRuntime:
    """Attribute view over entrypoint-owned capabilities without a module import."""

    def __init__(self, namespace: Mapping[str, Any]) -> None:
        self._namespace = namespace

    def __getattr__(self, name: str) -> Any:
        try:
            return self._namespace[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


_runtime: ServiceRuntime | None = None


def bind_service_runtime(namespace: Mapping[str, Any]) -> None:
    """Bind application capabilities after app assembly is complete.

    Services receive an attribute view rather than importing the FastAPI
    application module. Tests and runtime configuration can still replace an
    explicitly bound capability through the entrypoint namespace.
    """

    global _runtime
    _runtime = ServiceRuntime(namespace)


def service_runtime() -> ServiceRuntime:
    if _runtime is None:
        raise RuntimeError("service runtime has not been bound by the application entrypoint")
    return _runtime


def app_v2_module():
    """Compatibility name for services pending a local variable rename."""
    return service_runtime()

