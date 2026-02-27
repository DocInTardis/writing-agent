"""Init module.

This module belongs to `writing_agent.observability` in the writing-agent codebase.
"""

from writing_agent.observability.otel_bridge import OTelBridge, get_bridge

__all__ = ["OTelBridge", "get_bridge"]
