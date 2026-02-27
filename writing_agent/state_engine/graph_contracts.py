"""Graph Contracts module.

This module belongs to `writing_agent.state_engine` in the writing-agent codebase.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass(frozen=True)
class NodeSchema:
    """Lightweight node IO contract for graph orchestration."""

    input_fields: tuple[str, ...]
    output_fields: tuple[str, ...]


@dataclass(frozen=True)
class GraphNodeDef:
    node_id: str
    description: str
    schema: NodeSchema
    handler_name: str


@dataclass(frozen=True)
class GraphEdgeDef:
    source: str
    target: str
    condition: str = "always"


@dataclass(frozen=True)
class GraphRouteDef:
    route_id: str
    entry_node: str
    match: str


@dataclass(frozen=True)
class GraphDefinition:
    schema_version: str
    nodes: tuple[GraphNodeDef, ...]
    edges: tuple[GraphEdgeDef, ...]
    routes: tuple[GraphRouteDef, ...]


def default_graph_definition() -> GraphDefinition:
    """Single source of truth for explicit nodes/edges/routes used by native + langgraph engines."""

    nodes = (
        GraphNodeDef(
            node_id="planner",
            description="Build section plan and generation constraints",
            schema=NodeSchema(
                input_fields=("instruction", "current_text", "compose_mode", "resume_sections"),
                output_fields=("plan", "required_h2", "required_outline", "metadata"),
            ),
            handler_name="planner",
        ),
        GraphNodeDef(
            node_id="writer",
            description="Generate section/body content",
            schema=NodeSchema(
                input_fields=("plan", "instruction", "current_text", "format_only"),
                output_fields=("draft", "section_events", "metadata"),
            ),
            handler_name="writer",
        ),
        GraphNodeDef(
            node_id="reviewer",
            description="Run structure, citation, and consistency checks",
            schema=NodeSchema(
                input_fields=("draft", "plan", "policy"),
                output_fields=("review", "fixups", "metadata"),
            ),
            handler_name="reviewer",
        ),
        GraphNodeDef(
            node_id="qa",
            description="Finalize payload and quality envelope",
            schema=NodeSchema(
                input_fields=("draft", "review", "fixups"),
                output_fields=("final_text", "problems", "metadata"),
            ),
            handler_name="qa",
        ),
    )
    edges = (
        GraphEdgeDef(source="planner", target="writer"),
        GraphEdgeDef(source="writer", target="reviewer"),
        GraphEdgeDef(source="reviewer", target="qa"),
    )
    routes = (
        GraphRouteDef(route_id="compose_mode", entry_node="planner", match="compose_mode in {'auto','continue','overwrite'}"),
        GraphRouteDef(route_id="resume_sections", entry_node="planner", match="len(resume_sections)>0"),
        GraphRouteDef(route_id="format_only", entry_node="planner", match="format_only==true"),
    )
    return GraphDefinition(schema_version="1.0", nodes=nodes, edges=edges, routes=routes)


def node_map(definition: GraphDefinition) -> dict[str, GraphNodeDef]:
    return {n.node_id: n for n in definition.nodes}


def edge_map(definition: GraphDefinition) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for edge in definition.edges:
        out.setdefault(edge.source, []).append(edge.target)
    return out


def validate_contract(payload: dict[str, Any], schema: NodeSchema) -> tuple[bool, list[str]]:
    missing: list[str] = []
    for field in schema.input_fields:
        if field not in payload:
            missing.append(field)
    return (len(missing) == 0, missing)
