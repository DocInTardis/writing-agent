"""Base module.

This module belongs to `writing_agent.web.services` in the writing-agent codebase.
"""

from __future__ import annotations


def app_v2_module():
    """Lazy import to avoid circular dependency at module import time."""
    from writing_agent.web import app_v2

    return app_v2

