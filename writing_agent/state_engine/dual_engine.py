"""Dual Engine module.

This module belongs to `writing_agent.state_engine` in the writing-agent codebase.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from writing_agent.state_engine.checkpoint_store import CheckpointStore
from writing_agent.state_engine.graph_contracts import (
    GraphDefinition,
    default_graph_definition,
    edge_map,
    node_map,
    validate_contract,
)
from writing_agent.state_engine.replay import deterministic_replay


NodeHandler = Callable[[dict[str, Any]], dict[str, Any]]
InterruptHandler = Callable[[str, dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class EngineMetadata:
    trace_id: str
    span_id: str
    node_id: str
    engine: str
    started_at: float
    ended_at: float


class DualGraphEngine:
    """
    Self-hosted graph engine with optional LangGraph backend.

    Default behavior uses native execution order from explicit edges.
    Set `use_langgraph=True` to try langgraph.StateGraph when available.
    """

    def __init__(
        self,
        *,
        definition: GraphDefinition | None = None,
        checkpoint_store: CheckpointStore | None = None,
        use_langgraph: bool = False,
    ) -> None:
        self.definition = definition or default_graph_definition()
        self.checkpoints = checkpoint_store or CheckpointStore()
        self.use_langgraph = bool(use_langgraph)

    def run(
        self,
        *,
        run_id: str,
        payload: dict[str, Any],
        handlers: dict[str, NodeHandler],
        interrupts: dict[str, InterruptHandler] | None = None,
        resume: bool = False,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Execute graph using langgraph when requested, otherwise native engine."""
        if self.use_langgraph:
            try:
                return self._run_langgraph(run_id=run_id, payload=payload, handlers=handlers, interrupts=interrupts or {}, resume=resume)
            except Exception:
                pass
        return self._run_native(run_id=run_id, payload=payload, handlers=handlers, interrupts=interrupts or {}, resume=resume)

    def _run_native(
        self,
        *,
        run_id: str,
        payload: dict[str, Any],
        handlers: dict[str, NodeHandler],
        interrupts: dict[str, InterruptHandler],
        resume: bool,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Run explicit topological execution with contract checks and checkpoints."""
        state = dict(payload or {})
        trace_id = str(state.get("trace_id") or uuid.uuid4().hex)
        state.setdefault("trace_id", trace_id)
        state.setdefault("schema_version", self.definition.schema_version)
        self._seed_defaults(state)

        events: list[dict[str, Any]] = []
        if resume:
            saved = self.checkpoints.load(run_id)
            if isinstance(saved, dict):
                prior = saved.get("events") if isinstance(saved.get("events"), list) else []
                restored = deterministic_replay(prior)
                state.update(restored)
                events.extend(prior)
                self._seed_defaults(state)

        order = self._topological_order()
        nodes = node_map(self.definition)
        for node_id in order:
            node_def = nodes[node_id]
            handler = handlers.get(node_def.handler_name)
            if handler is None:
                continue
            ok, missing = validate_contract(state, node_def.schema)
            if not ok:
                raise ValueError(f"node {node_id} missing required input fields: {','.join(missing)}")

            if node_id in interrupts:
                decision = interrupts[node_id](node_id, dict(state))
                if isinstance(decision, dict) and decision.get("action") == "pause":
                    pause_event = {
                        "node_id": node_id,
                        "status": "interrupted",
                        "patch": dict(decision.get("patch") or {}),
                        "metadata": {
                            "trace_id": trace_id,
                            "span_id": uuid.uuid4().hex,
                            "node_id": node_id,
                            "engine": "native",
                            "started_at": time.time(),
                            "ended_at": time.time(),
                        },
                    }
                    state.update(dict(pause_event["patch"]))
                    events.append(pause_event)
                    self.checkpoints.save(run_id, state, events)
                    return state, events

            started = time.time()
            patch = handler(dict(state)) or {}
            ended = time.time()
            metadata = {
                "trace_id": trace_id,
                "span_id": uuid.uuid4().hex,
                "node_id": node_id,
                "engine": "native",
                "started_at": started,
                "ended_at": ended,
            }
            state.update(dict(patch))
            event = {"node_id": node_id, "status": "ok", "patch": dict(patch), "metadata": metadata}
            events.append(event)
            self.checkpoints.save(run_id, state, events)
        return state, events

    def _run_langgraph(
        self,
        *,
        run_id: str,
        payload: dict[str, Any],
        handlers: dict[str, NodeHandler],
        interrupts: dict[str, InterruptHandler],
        resume: bool,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Run graph with LangGraph StateGraph when dependency is available."""
        # Optional dependency path. If unavailable, caller falls back to native engine.
        from langgraph.graph import END, StateGraph  # type: ignore

        state = dict(payload or {})
        trace_id = str(state.get("trace_id") or uuid.uuid4().hex)
        state.setdefault("trace_id", trace_id)
        state.setdefault("schema_version", self.definition.schema_version)
        self._seed_defaults(state)

        events: list[dict[str, Any]] = []
        if resume:
            saved = self.checkpoints.load(run_id)
            if isinstance(saved, dict):
                prior = saved.get("events") if isinstance(saved.get("events"), list) else []
                restored = deterministic_replay(prior)
                state.update(restored)
                events.extend(prior)
                self._seed_defaults(state)

        graph = StateGraph(dict)

        for node in self.definition.nodes:
            handler = handlers.get(node.handler_name)
            if handler is None:
                continue

            def _mk(node_id: str, schema=node.schema, fn=handler):
                def _runner(data: dict[str, Any]) -> dict[str, Any]:
                    ok, missing = validate_contract(data, schema)
                    if not ok:
                        raise ValueError(f"node {node_id} missing required input fields: {','.join(missing)}")
                    if node_id in interrupts:
                        decision = interrupts[node_id](node_id, dict(data))
                        if isinstance(decision, dict) and decision.get("action") == "pause":
                            patch = dict(decision.get("patch") or {})
                            data.update(patch)
                            events.append(
                                {
                                    "node_id": node_id,
                                    "status": "interrupted",
                                    "patch": patch,
                                    "metadata": {
                                        "trace_id": trace_id,
                                        "span_id": uuid.uuid4().hex,
                                        "node_id": node_id,
                                        "engine": "langgraph",
                                        "started_at": time.time(),
                                        "ended_at": time.time(),
                                    },
                                }
                            )
                            self.checkpoints.save(run_id, data, events)
                            return data
                    started = time.time()
                    patch = fn(dict(data)) or {}
                    ended = time.time()
                    data.update(dict(patch))
                    events.append(
                        {
                            "node_id": node_id,
                            "status": "ok",
                            "patch": dict(patch),
                            "metadata": {
                                "trace_id": trace_id,
                                "span_id": uuid.uuid4().hex,
                                "node_id": node_id,
                                "engine": "langgraph",
                                "started_at": started,
                                "ended_at": ended,
                            },
                        }
                    )
                    self.checkpoints.save(run_id, data, events)
                    return data

                return _runner

            graph.add_node(node.node_id, _mk(node.node_id))

        order = self._topological_order()
        if not order:
            return state, events
        graph.set_entry_point(order[0])
        adjacency = edge_map(self.definition)
        for src, targets in adjacency.items():
            for target in targets:
                graph.add_edge(src, target)
        graph.add_edge(order[-1], END)
        app = graph.compile()
        final_state = app.invoke(state)
        return dict(final_state or {}), events

    def _topological_order(self) -> list[str]:
        """Compute deterministic node order from declared edges."""
        nodes = [n.node_id for n in self.definition.nodes]
        adjacency = edge_map(self.definition)
        indeg: dict[str, int] = {n: 0 for n in nodes}
        for src, targets in adjacency.items():
            if src not in indeg:
                indeg[src] = 0
            for t in targets:
                indeg[t] = indeg.get(t, 0) + 1
        queue: list[str] = [n for n in nodes if indeg.get(n, 0) == 0]
        order: list[str] = []
        while queue:
            cur = queue.pop(0)
            order.append(cur)
            for nxt in adjacency.get(cur, []):
                indeg[nxt] = indeg.get(nxt, 0) - 1
                if indeg[nxt] == 0:
                    queue.append(nxt)
        if len(order) != len(nodes):
            # fall back to declared order
            return nodes
        return order

    def _seed_defaults(self, state: dict[str, Any]) -> None:
        """Populate default fields required by graph node contracts."""
        state.setdefault("compose_mode", "auto")
        state.setdefault("resume_sections", [])
        state.setdefault("format_only", False)
        state.setdefault("policy", {})


def should_use_langgraph() -> bool:
    """Environment switch for selecting graph backend."""
    import os

    raw = str(os.environ.get("WRITING_AGENT_GRAPH_ENGINE", "native")).strip().lower()
    return raw in {"langgraph", "dual", "auto"}
