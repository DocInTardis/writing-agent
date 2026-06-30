"""KG-RAG retriever — query entity linking + graph traversal + KU ranking.

Integrates with existing RAG as a secondary, high-precision ranking layer.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from writing_agent.v2.rag.knowledge_graph import KGEntity, KGRelation, KnowledgeGraph
from writing_agent.v2.rag.knowledge_unit import KnowledgeUnit, KUStore

logger = logging.getLogger(__name__)


class KGRetriever:
    """Retrieve knowledge units via graph traversal.

    Pipeline:
        1. Extract query entities (simple keyword overlap)
        2. BFS traversal from matched entities
        3. Score KUs by graph distance + entity overlap
        4. Return ranked KnowledgeUnits with provenance
    """

    def __init__(
        self,
        store: KUStore | None = None,
        graph: KnowledgeGraph | None = None,
        graph_path: Path | None = None,
    ) -> None:
        self.store = store
        self.graph = graph or KnowledgeGraph()
        self._graph_path = graph_path
        if graph_path and graph_path.exists():
            self.graph.load(graph_path)
        self._ku_index: dict[str, KnowledgeUnit] | None = None

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def retrieve(
        self,
        query: str,
        top_k: int = 4,
        max_depth: int = 2,
        min_confidence: float = 0.5,
    ) -> list[KnowledgeUnit]:
        """Main entry: rank KUs relevant to the query using the graph."""
        if not self.graph.entities:
            logger.debug("KG empty; returning empty result")
            return []

        # 1. Entity linking via keyword overlap
        linked = self._link_entities(query)
        if not linked:
            logger.debug("No entity linked for query: %s", query[:60])
            return []

        # 2. BFS from linked entities and score
        scores: dict[str, float] = {}
        for ent_id in linked:
            result = self.graph.traverse(ent_id, max_depth=max_depth)
            for node in result["nodes"]:
                node_id = node["id"]
                dist = result["distances"].get(node_id, max_depth + 1)
                score = 1.0 / (1.0 + dist)
                for ku_id in node.get("ku_ids", []):
                    scores[ku_id] = scores.get(ku_id, 0.0) + score

        # 3. Load KUs and apply confidence filter + sort
        ku_index = self._build_ku_index()
        ranked = []
        for ku_id, score in sorted(scores.items(), key=lambda x: x[1], reverse=True):
            ku = ku_index.get(ku_id)
            if ku is None:
                continue
            if ku.confidence < min_confidence:
                continue
            ranked.append(ku)
            if len(ranked) >= top_k:
                break

        logger.debug("KG retrieved %d units for query", len(ranked))
        return ranked

    def retrieve_with_trail(
        self,
        query: str,
        top_k: int = 4,
        max_depth: int = 2,
        min_confidence: float = 0.5,
    ) -> dict[str, Any]:
        """Same as retrieve but includes audit trail for provenance."""
        units = self.retrieve(query, top_k, max_depth, min_confidence)
        trail = {
            "query": query,
            "linked_entities": self._link_entities(query),
            "retrieved_ku_ids": [u.ku_id for u in units],
            "max_depth": max_depth,
            "top_k": top_k,
        }
        return {"units": units, "trail": trail}

    # ------------------------------------------------------------------ #
    # Entity linking
    # ------------------------------------------------------------------ #

    def _link_entities(self, query: str) -> list[str]:
        """Match query tokens against entity names. Returns matched entity IDs."""
        query_lower = query.lower()
        tokens = set(query_lower.split())
        matched: list[str] = []
        for ent in self.graph.entities.values():
            name_lower = ent.name.lower()
            # Exact substring match or token overlap
            if name_lower in query_lower or query_lower in name_lower:
                matched.append(ent.id)
                continue
            ent_tokens = set(name_lower.split())
            if len(ent_tokens) >= 2 and len(ent_tokens & tokens) >= 2:
                matched.append(ent.id)
            elif len(ent_tokens) == 1 and ent_tokens.issubset(tokens):
                matched.append(ent.id)
        return matched

    # ------------------------------------------------------------------ #
    # Indexing helpers
    # ------------------------------------------------------------------ #

    def _build_ku_index(self) -> dict[str, KnowledgeUnit]:
        if self._ku_index is not None:
            return self._ku_index
        if self.store is None:
            self._ku_index = {}
            return self._ku_index
        units = self.store.load()
        self._ku_index = {u.ku_id: u for u in units}
        return self._ku_index

    def refresh_index(self) -> None:
        """Invalidate KU index (call after store updates)."""
        self._ku_index = None
        if self._graph_path:
            self.graph.load(self._graph_path)

    # ------------------------------------------------------------------ #
    # Graph construction helpers
    # ------------------------------------------------------------------ #

    def build_graph(self) -> None:
        """Rebuild graph from current store contents."""
        if self.store is None:
            raise ValueError("KUStore required to build graph")
        units = self.store.load()
        self.graph = KnowledgeGraph()
        self.graph.build_from_kus(units)
        self._ku_index = None
        logger.info("Built KG: %s", self.graph.stats())

    def persist(self, path: Path | None = None) -> None:
        target = path or self._graph_path
        if target is None:
            raise ValueError("No graph path configured")
        self.graph.save(target)
        logger.info("Persisted KG to %s", target)
