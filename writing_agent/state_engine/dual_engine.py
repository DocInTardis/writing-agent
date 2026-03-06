"""Dual Engine module.

This module belongs to `writing_agent.state_engine` in the writing-agent codebase.
"""

from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from writing_agent.state_engine.checkpoint_store import CheckpointStore
from writing_agent.state_engine.graph_contracts import (
    GraphDefinition,
    GraphRouteDef,
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
                saved_state = saved.get("state") if isinstance(saved.get("state"), dict) else {}
                prior_route = saved_state.get("_route") if isinstance(saved_state, dict) else None
                if isinstance(prior_route, dict):
                    state["_route"] = {
                        "id": str(prior_route.get("id") or "").strip(),
                        "entry_node": str(prior_route.get("entry_node") or "").strip(),
                    }
                events.extend(prior)
                self._seed_defaults(state)

        route = self._resolve_route(state)
        self._apply_route_defaults(state, route)
        route_id = str(route.route_id) if route else "default"
        route_entry = str(route.entry_node) if route else ""
        state["_route"] = {"id": route_id, "entry_node": route_entry}

        order = self._execution_order(entry_node=route.entry_node if route else None)
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
                            "route_id": route_id,
                            "route_entry": route_entry,
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
                "route_id": route_id,
                "route_entry": route_entry,
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
                saved_state = saved.get("state") if isinstance(saved.get("state"), dict) else {}
                prior_route = saved_state.get("_route") if isinstance(saved_state, dict) else None
                if isinstance(prior_route, dict):
                    state["_route"] = {
                        "id": str(prior_route.get("id") or "").strip(),
                        "entry_node": str(prior_route.get("entry_node") or "").strip(),
                    }
                events.extend(prior)
                self._seed_defaults(state)

        route = self._resolve_route(state)
        self._apply_route_defaults(state, route)
        route_id = str(route.route_id) if route else "default"
        route_entry = str(route.entry_node) if route else ""
        state["_route"] = {"id": route_id, "entry_node": route_entry}

        graph = StateGraph(dict)
        available_nodes: set[str] = set()

        for node in self.definition.nodes:
            handler = handlers.get(node.handler_name)
            if handler is None:
                continue
            available_nodes.add(node.node_id)

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
                                        "route_id": route_id,
                                        "route_entry": route_entry,
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
                                "route_id": route_id,
                                "route_entry": route_entry,
                                "started_at": started,
                                "ended_at": ended,
                            },
                        }
                    )
                    self.checkpoints.save(run_id, data, events)
                    return data

                return _runner

            graph.add_node(node.node_id, _mk(node.node_id))

        order = self._execution_order(entry_node=route.entry_node if route else None)
        if not order:
            return state, events
        route_nodes = set(order)
        entry_node = next((node_id for node_id in order if node_id in available_nodes), None)
        if not entry_node:
            return state, events
        graph.set_entry_point(entry_node)
        adjacency = edge_map(self.definition)
        for src, targets in adjacency.items():
            for target in targets:
                if src not in route_nodes or target not in route_nodes:
                    continue
                if src not in available_nodes or target not in available_nodes:
                    continue
                graph.add_edge(src, target)
        exit_node = next((node_id for node_id in reversed(order) if node_id in available_nodes), None)
        if exit_node:
            graph.add_edge(exit_node, END)
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

    def _execution_order(self, *, entry_node: str | None = None) -> list[str]:
        order = self._topological_order()
        if not entry_node:
            return order
        entry = str(entry_node).strip()
        if not entry or entry not in order:
            return order
        adjacency = edge_map(self.definition)
        reachable: set[str] = set()
        queue: list[str] = [entry]
        while queue:
            cur = queue.pop(0)
            if cur in reachable:
                continue
            reachable.add(cur)
            for nxt in adjacency.get(cur, []):
                if nxt not in reachable:
                    queue.append(nxt)
        selected = [node_id for node_id in order if node_id in reachable]
        return selected or order

    def _resolve_route(self, state: dict[str, Any]) -> GraphRouteDef | None:
        routes = list(self.definition.routes or ())
        if not routes:
            return None
        map_by_id = {str(route.route_id): route for route in routes}
        prior = state.get("_route")
        if isinstance(prior, dict):
            prior_id = str(prior.get("id") or "").strip()
            if prior_id and prior_id in map_by_id:
                return map_by_id[prior_id]
        for route in routes:
            if self._route_match(route.match, state):
                return route
        return None

    def _route_match(self, expr: str, state: dict[str, Any]) -> bool:
        raw = str(expr or "").strip()
        if not raw:
            return False
        # Normalize booleans from config-style strings to Python literals.
        py_expr = re.sub(r"\btrue\b", "True", raw, flags=re.IGNORECASE)
        py_expr = re.sub(r"\bfalse\b", "False", py_expr, flags=re.IGNORECASE)
        env: dict[str, Any] = dict(state or {})
        env.setdefault("compose_mode", "auto")
        env.setdefault("resume_sections", [])
        env.setdefault("format_only", False)
        try:
            out = eval(py_expr, {"__builtins__": {}, "len": len}, env)
            return bool(out)
        except Exception:
            return False

    def _apply_route_defaults(self, state: dict[str, Any], route: GraphRouteDef | None) -> None:
        if route is None:
            return
        route_id = str(route.route_id or "").strip().lower()
        if route_id == "resume_sections":
            state.setdefault(
                "plan",
                {
                    "compose_mode": str(state.get("compose_mode") or "auto"),
                    "resume_sections": list(state.get("resume_sections") or []),
                },
            )
        elif route_id == "format_only":
            state.setdefault("draft", str(state.get("current_text") or ""))
            state.setdefault("review", {"issues": []})
            state.setdefault("fixups", [])

    def _seed_defaults(self, state: dict[str, Any]) -> None:
        """Populate default fields required by graph node contracts."""
        state.setdefault("compose_mode", "auto")
        state.setdefault("resume_sections", [])
        state.setdefault("format_only", False)
        state.setdefault("policy", {})
        state.setdefault("plan_confirm", {"decision": "approved", "score": 0, "note": ""})
        state.setdefault("plan_confirmed", True)


def should_use_langgraph() -> bool:
    """Environment switch for selecting graph backend."""
    import os

    raw = str(os.environ.get("WRITING_AGENT_GRAPH_ENGINE", "native")).strip().lower()
    return raw in {"langgraph", "dual", "auto"}
