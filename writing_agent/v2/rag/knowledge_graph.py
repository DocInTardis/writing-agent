"""Lightweight knowledge graph backed by dicts (NetworkX optional upgrade path).

Stores entities and relations extracted from KnowledgeUnits.
Supports BFS traversal for retrieval and JSON serialization.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from writing_agent.v2.rag.knowledge_unit import KnowledgeUnit

logger = logging.getLogger(__name__)


class KGEntity(BaseModel):
    """A node in the knowledge graph."""

    model_config = ConfigDict(validate_assignment=True)

    id: str = Field(..., description="Stable entity ID")
    name: str = Field(..., min_length=1, description="Human-readable name")
    entity_type: str = Field(
        default="concept",
        pattern=r"^(method|dataset|concept|claim|author|metric)$",
        description="Entity category",
    )
    # Back-references to originating KUs
    ku_ids: list[str] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str) -> str:
        return v.strip()


class KGRelation(BaseModel):
    """An edge in the knowledge graph."""

    model_config = ConfigDict(validate_assignment=True)

    from_id: str
    to_id: str
    relation: str = Field(
        default="related",
        pattern=r"^(supports|contradicts|extends|cites|uses|compares|related)$",
    )
    weight: float = Field(default=1.0, ge=0.0, le=10.0)
    # Optional provenance
    source_ku_id: str = ""


class KnowledgeGraph:
    """In-memory knowledge graph with JSON persistence.

    Uses plain dicts for speed and zero extra dependencies.
    NetworkX can be swapped in later if advanced analytics are needed.
    """

    def __init__(self) -> None:
        self.entities: dict[str, KGEntity] = {}
        self.relations: list[KGRelation] = []
        # Index: entity_id -> list of relation indices for fast traversal
        self._adj: dict[str, list[int]] = {}

    # ------------------------------------------------------------------ #
    # Building
    # ------------------------------------------------------------------ #

    def add_entity(self, entity: KGEntity) -> KGEntity:
        """Idempotent add; merges ku_ids if entity already exists."""
        key = entity.id
        if key in self.entities:
            existing = self.entities[key]
            merged_kus = list(dict.fromkeys(existing.ku_ids + entity.ku_ids))
            existing = existing.model_copy(update={"ku_ids": merged_kus})
            self.entities[key] = existing
            return existing
        self.entities[key] = entity
        self._adj.setdefault(key, [])
        return entity

    def add_relation(self, relation: KGRelation) -> None:
        """Add relation if both endpoints exist."""
        if relation.from_id not in self.entities or relation.to_id not in self.entities:
            logger.debug(
                "Skipping relation %s -> %s (missing endpoint)",
                relation.from_id,
                relation.to_id,
            )
            return
        idx = len(self.relations)
        self.relations.append(relation)
        self._adj.setdefault(relation.from_id, []).append(idx)
        self._adj.setdefault(relation.to_id, []).append(idx)

    def build_from_kus(self, units: list[KnowledgeUnit]) -> None:
        """Populate graph from a list of KnowledgeUnits."""
        for u in units:
            # Add KU itself as a claim entity
            claim_ent = KGEntity(
                id=u.ku_id,
                name=u.claim[:120],
                entity_type="claim",
                ku_ids=[u.ku_id],
            )
            self.add_entity(claim_ent)

            # Add extracted entities
            for ent_name in u.entities:
                ent_id = self._entity_id(ent_name)
                ent = KGEntity(
                    id=ent_id,
                    name=ent_name,
                    entity_type=self._infer_type(ent_name),
                    ku_ids=[u.ku_id],
                )
                self.add_entity(ent)
                # Link claim -> entity (uses)
                self.add_relation(
                    KGRelation(
                        from_id=u.ku_id,
                        to_id=ent_id,
                        relation="uses",
                        source_ku_id=u.ku_id,
                    )
                )

            # Add relation hints from LLM extraction
            for hint in u.relation_hints:
                if hint not in {"supports", "contradicts", "extends", "cites", "uses", "compares"}:
                    continue
                # relation_hint on first entity -> claim direction
                if u.entities:
                    self.add_relation(
                        KGRelation(
                            from_id=self._entity_id(u.entities[0]),
                            to_id=u.ku_id,
                            relation=hint,
                            source_ku_id=u.ku_id,
                        )
                    )

    @staticmethod
    def _entity_id(name: str) -> str:
        """Deterministic ID from entity name."""
        import hashlib

        return f"ENT-{hashlib.sha1(name.strip().lower().encode()).hexdigest()[:12]}"

    @staticmethod
    def _infer_type(name: str) -> str:
        """Heuristic entity type inference."""
        lowered = name.lower()
        if any(s in lowered for s in ("bert", "gpt", "transformer", "cnn", "rnn", "lstm", "gan")):
            return "method"
        if any(s in lowered for s in ("imagenet", "coco", "mnist", "squad", "glue")):
            return "dataset"
        if any(s in lowered for s in ("accuracy", "f1", "bleu", "rouge", "map")):
            return "metric"
        if " " not in name and name[0].isupper() and len(name) < 30:
            return "author"
        return "concept"

    # ------------------------------------------------------------------ #
    # Traversal
    # ------------------------------------------------------------------ #

    def traverse(
        self,
        start_entity_id: str,
        max_depth: int = 2,
        relation_filter: set[str] | None = None,
    ) -> dict[str, Any]:
        """BFS from a start entity, returning visited nodes and distances."""
        if start_entity_id not in self.entities:
            return {"nodes": [], "distances": {}}

        visited: set[str] = {start_entity_id}
        distances: dict[str, int] = {start_entity_id: 0}
        queue: list[tuple[str, int]] = [(start_entity_id, 0)]
        result_nodes: list[dict[str, Any]] = []

        while queue:
            current, depth = queue.pop(0)
            if depth >= max_depth:
                continue
            ent = self.entities.get(current)
            if ent is None:
                continue
            result_nodes.append(ent.model_dump())

            for rel_idx in self._adj.get(current, []):
                rel = self.relations[rel_idx]
                if relation_filter and rel.relation not in relation_filter:
                    continue
                neighbor = rel.to_id if rel.from_id == current else rel.from_id
                if neighbor not in visited:
                    visited.add(neighbor)
                    distances[neighbor] = depth + 1
                    queue.append((neighbor, depth + 1))

        return {"nodes": result_nodes, "distances": distances}

    def get_neighbors(
        self,
        entity_id: str,
        relation_filter: set[str] | None = None,
    ) -> list[tuple[KGEntity, KGRelation]]:
        """Return (neighbor_entity, relation) tuples for a given entity."""
        out: list[tuple[KGEntity, KGRelation]] = []
        for rel_idx in self._adj.get(entity_id, []):
            rel = self.relations[rel_idx]
            if relation_filter and rel.relation not in relation_filter:
                continue
            neighbor_id = rel.to_id if rel.from_id == entity_id else rel.from_id
            neighbor = self.entities.get(neighbor_id)
            if neighbor:
                out.append((neighbor, rel))
        return out

    # ------------------------------------------------------------------ #
    # Persistence
    # ------------------------------------------------------------------ #

    def save(self, path: Path) -> None:
        data = {
            "entities": [e.model_dump() for e in self.entities.values()],
            "relations": [r.model_dump() for r in self.relations],
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def load(self, path: Path) -> None:
        if not path.exists():
            return
        raw = json.loads(path.read_text(encoding="utf-8"))
        self.entities = {}
        self.relations = []
        self._adj = {}
        for e in raw.get("entities", []):
            ent = KGEntity.model_validate(e)
            self.entities[ent.id] = ent
            self._adj.setdefault(ent.id, [])
        for r in raw.get("relations", []):
            rel = KGRelation.model_validate(r)
            idx = len(self.relations)
            self.relations.append(rel)
            self._adj.setdefault(rel.from_id, []).append(idx)
            self._adj.setdefault(rel.to_id, []).append(idx)

    def stats(self) -> dict[str, int]:
        return {
            "entities": len(self.entities),
            "relations": len(self.relations),
        }
