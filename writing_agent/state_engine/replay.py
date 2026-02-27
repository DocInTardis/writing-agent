"""Replay module.

This module belongs to `writing_agent.state_engine` in the writing-agent codebase.
"""

from __future__ import annotations

from typing import Any


def deterministic_replay(events: list[dict[str, Any]]) -> dict[str, Any]:
    """Deterministically rebuild terminal state from ordered node events."""

    state: dict[str, Any] = {}
    for row in events or []:
        if not isinstance(row, dict):
            continue
        patch = row.get("patch") if isinstance(row.get("patch"), dict) else {}
        state.update(patch)
        meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        if meta:
            state.setdefault("_replay_meta", []).append(meta)
    return state


def replay_summary(events: list[dict[str, Any]]) -> dict[str, Any]:
    by_node: dict[str, int] = {}
    for row in events or []:
        node_id = str((row or {}).get("node_id") or "unknown")
        by_node[node_id] = by_node.get(node_id, 0) + 1
    return {
        "event_count": len(events or []),
        "node_counts": by_node,
    }
