"""Notion exporter for KnowledgeUnits.

Writes KUs to a Notion Database with schema:
    Claim (title), Evidence (rich_text), Source (url), Page (number),
    Confidence (number), Status (select)

Rate-limit aware: ~3 req/sec max, uses simple time.sleep throttling.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Any

from writing_agent.v2.rag.knowledge_unit import KnowledgeUnit

logger = logging.getLogger(__name__)

# Notion rate-limit guidance for integration tier: ~3 req/sec
_MIN_INTERVAL_S = 0.35


@dataclass
class NotionExportConfig:
    token: str
    database_id: str
    status_default: str = "审核中"


class NotionExporter:
    """Export KnowledgeUnits to a Notion Database.

    Requires a WRITING_AGENT_NOTION_TOKEN env var and a database_id.
    """

    def __init__(self, config: NotionExportConfig | None = None) -> None:
        self._client: Any = None
        self.config = config

    @property
    def client(self) -> Any:
        if self._client is None:
            token = self.config.token if self.config else os.environ.get("WRITING_AGENT_NOTION_TOKEN", "")
            if not token:
                raise ValueError("Notion token missing (WRITING_AGENT_NOTION_TOKEN)")
            try:
                from notion_client import Client
            except Exception as exc:
                raise ImportError("notion-client not installed") from exc
            self._client = Client(auth=token)
        return self._client

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def export_units(
        self,
        units: list[KnowledgeUnit],
        *,
        database_id: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """Batch-export KUs as pages in a Notion Database.

        Returns list of created page objects for auditing.
        """
        db_id = database_id or (self.config.database_id if self.config else "")
        if not db_id:
            raise ValueError("database_id required")
        default_status = status or (self.config.status_default if self.config else "审核中")

        results: list[dict[str, Any]] = []
        for u in units:
            try:
                page = self._create_page(u, db_id, default_status)
                results.append(page)
            except Exception as exc:
                logger.warning("Failed to export KU %s to Notion: %s", u.ku_id, exc)
            time.sleep(_MIN_INTERVAL_S)
        logger.info("Exported %d/%d KUs to Notion DB %s", len(results), len(units), db_id)
        return results

    def sync_relations(
        self,
        units: list[KnowledgeUnit],
        page_map: dict[str, str],
    ) -> int:
        """Update Notion pages to add relation links between KUs sharing entities.

        page_map: ku_id -> notion_page_id
        Returns number of updates applied.
        """
        updated = 0
        for u in units:
            page_id = page_map.get(u.ku_id)
            if not page_id:
                continue
            related = self._find_related_ku_ids(u, units)
            relation_ids = [page_map[r] for r in related if r in page_map]
            if not relation_ids:
                continue
            try:
                self._update_page_relations(page_id, relation_ids)
                updated += 1
            except Exception as exc:
                logger.warning("Failed to update relations for %s: %s", u.ku_id, exc)
            time.sleep(_MIN_INTERVAL_S)
        return updated

    def import_feedback(
        self,
        database_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Query Notion DB for pages with user-modified Status/Comment.

        Returns list of {ku_id, status, comment, notion_page_id} dicts.
        """
        db_id = database_id or (self.config.database_id if self.config else "")
        if not db_id:
            raise ValueError("database_id required")

        try:
            response = self.client.databases.query(database_id=db_id)
        except Exception as exc:
            logger.warning("Failed to query Notion DB: %s", exc)
            return []

        feedback: list[dict[str, Any]] = []
        for page in response.get("results", []):
            props = page.get("properties", {})
            ku_id = self._extract_rich_text(props.get("KU ID", {}))
            status = self._extract_select(props.get("Status", {}))
            comment = self._extract_rich_text(props.get("Comment", {}))
            if ku_id or status or comment:
                feedback.append({
                    "ku_id": ku_id,
                    "status": status,
                    "comment": comment,
                    "notion_page_id": page.get("id"),
                })
        return feedback

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _create_page(
        self,
        unit: KnowledgeUnit,
        database_id: str,
        status: str,
    ) -> dict[str, Any]:
        properties = {
            "Claim": {"title": [{"text": {"content": unit.claim[:500]}}]},
            "Evidence": {"rich_text": [{"text": {"content": (unit.evidence or "")[:2000]}}]},
            "Source": {"url": unit.source_doc if unit.source_doc.startswith("http") else None},
            "Page": {"number": unit.source_page},
            "Confidence": {"number": round(unit.confidence, 2)},
            "Status": {"select": {"name": status}},
            "KU ID": {"rich_text": [{"text": {"content": unit.ku_id}}]},
        }
        # Clean None values for Notion API
        properties = {k: v for k, v in properties.items() if v is not None and (not isinstance(v, dict) or "url" not in v or v["url"] is not None)}
        if "Page" in properties and unit.source_page is None:
            del properties["Page"]
        return self.client.pages.create(parent={"database_id": database_id}, properties=properties)

    @staticmethod
    def _find_related_ku_ids(unit: KnowledgeUnit, all_units: list[KnowledgeUnit]) -> list[str]:
        related: list[str] = []
        unit_entities = set(e.lower() for e in unit.entities)
        for other in all_units:
            if other.ku_id == unit.ku_id:
                continue
            other_entities = set(e.lower() for e in other.entities)
            if unit_entities & other_entities:
                related.append(other.ku_id)
        return related[:10]  # cap relations per page

    def _update_page_relations(self, page_id: str, relation_ids: list[str]) -> None:
        # Notion relation property requires page IDs
        self.client.pages.update(
            page_id=page_id,
            properties={"Related KUs": {"relation": [{"id": rid} for rid in relation_ids]}},
        )

    @staticmethod
    def _extract_rich_text(prop: dict[str, Any]) -> str:
        rt = prop.get("rich_text", [])
        if rt:
            return str(rt[0].get("text", {}).get("content", ""))
        return ""

    @staticmethod
    def _extract_select(prop: dict[str, Any]) -> str:
        sel = prop.get("select")
        if sel:
            return str(sel.get("name", ""))
        return ""
