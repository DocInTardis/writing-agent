"""Spec module.

This module belongs to `writing_agent.diagrams` in the writing-agent codebase.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


DiagramType = Literal["flowchart", "er"]


@dataclass(frozen=True)
class FlowNode:
    id: str
    text: str


@dataclass(frozen=True)
class FlowEdge:
    src: str
    dst: str
    label: str = ""


@dataclass(frozen=True)
class FlowchartSpec:
    nodes: list[FlowNode] = field(default_factory=list)
    edges: list[FlowEdge] = field(default_factory=list)


@dataclass(frozen=True)
class ErEntity:
    name: str
    attributes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ErRelation:
    left: str
    right: str
    label: str = ""
    cardinality: str = ""  # e.g. "1..N"


@dataclass(frozen=True)
class ErSpec:
    entities: list[ErEntity] = field(default_factory=list)
    relations: list[ErRelation] = field(default_factory=list)


@dataclass(frozen=True)
class DiagramSpec:
    type: DiagramType
    title: str
    caption: str
    flowchart: FlowchartSpec | None = None
    er: ErSpec | None = None

