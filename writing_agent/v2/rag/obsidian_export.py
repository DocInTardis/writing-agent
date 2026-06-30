"""Obsidian vault exporter for KnowledgeUnits.

Generates Markdown + YAML frontmatter files compatible with Obsidian.
Uses Wikilink format for entity cross-referencing.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from writing_agent.v2.rag.knowledge_unit import KnowledgeUnit

logger = logging.getLogger(__name__)


def export_to_obsidian_vault(
    units: list[KnowledgeUnit],
    vault_dir: Path,
    *,
    subdir: str = "knowledge_units",
) -> list[Path]:
    """Write KUs as Markdown files into an Obsidian vault.

    Returns list of written file paths.
    """
    out_dir = Path(vault_dir) / subdir
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for u in units:
        safe_name = _safe_filename(u.claim[:60])
        path = out_dir / f"{safe_name}.md"
        content = _to_obsidian_md(u)
        path.write_text(content, encoding="utf-8")
        written.append(path)

    logger.info("Wrote %d KU pages to Obsidian vault %s", len(written), out_dir)
    return written


def import_from_obsidian(vault_dir: Path, *, subdir: str = "knowledge_units") -> list[KnowledgeUnit]:
    """Read back modified Markdown files and convert to KnowledgeUnits.

    Best-effort: skips files that cannot be parsed.
    """
    in_dir = Path(vault_dir) / subdir
    if not in_dir.exists():
        return []

    units: list[KnowledgeUnit] = []
    for path in in_dir.glob("*.md"):
        try:
            raw = path.read_text(encoding="utf-8")
            ku = _parse_obsidian_md(raw)
            if ku:
                units.append(ku)
        except Exception as exc:
            logger.debug("Skip %s: %s", path.name, exc)
    return units


def _to_obsidian_md(u: KnowledgeUnit) -> str:
    front = {
        "ku_id": u.ku_id,
        "source_doc": u.source_doc,
        "source_title": u.source_title,
        "source_authors": u.source_authors,
        "source_page": u.source_page,
        "source_para": u.source_para,
        "confidence": u.confidence,
        "entities": u.entities,
        "relation_hints": u.relation_hints,
    }
    yaml_block = json.dumps(front, ensure_ascii=False, indent=2)
    entities_links = " ".join(f"[[{e}]]" for e in u.entities)
    return (
        f"---\n{yaml_block}\n---\n\n"
        f"## Claim\n\n{u.claim}\n\n"
        f"## Evidence\n\n> {u.evidence}\n\n"
        f"## Entities\n\n{entities_links}\n"
    )


def _parse_obsidian_md(raw: str) -> KnowledgeUnit | None:
    lines = raw.splitlines()
    if len(lines) < 3:
        return None
    # Extract YAML frontmatter between --- markers
    if not lines[0].strip() == "---":
        return None
    yaml_lines: list[str] = []
    idx = 1
    while idx < len(lines) and lines[idx].strip() != "---":
        yaml_lines.append(lines[idx])
        idx += 1
    if idx >= len(lines):
        return None
    try:
        meta = json.loads("\n".join(yaml_lines))
    except Exception:
        return None

    # Extract claim / evidence from Markdown body
    claim = ""
    evidence = ""
    in_claim = False
    in_evidence = False
    for line in lines[idx + 1 :]:
        stripped = line.strip()
        if stripped == "## Claim":
            in_claim = True
            in_evidence = False
            continue
        if stripped == "## Evidence":
            in_claim = False
            in_evidence = True
            continue
        if stripped.startswith("## "):
            in_claim = False
            in_evidence = False
            continue
        if in_claim and stripped:
            claim = stripped
            in_claim = False
        if in_evidence and stripped:
            evidence = stripped.lstrip("> ")
            in_evidence = False

    if not claim or not evidence:
        return None

    return KnowledgeUnit(
        ku_id=meta.get("ku_id", ""),
        claim=claim,
        evidence=evidence,
        source_doc=meta.get("source_doc", ""),
        source_title=meta.get("source_title", ""),
        source_authors=meta.get("source_authors", []),
        source_page=meta.get("source_page"),
        source_para=meta.get("source_para"),
        confidence=meta.get("confidence", 0.8),
        entities=meta.get("entities", []),
        relation_hints=meta.get("relation_hints", []),
    )


def _safe_filename(name: str) -> str:
    """Sanitize a string for use as a filename."""
    forbidden = '\\/:*?"<>|'
    for ch in forbidden:
        name = name.replace(ch, "_")
    return name.strip().replace(" ", "_") or "untitled"
