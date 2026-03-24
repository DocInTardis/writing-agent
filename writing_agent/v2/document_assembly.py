"""Stable document assembly by section id."""

from __future__ import annotations

from dataclasses import dataclass

from writing_agent.v2.section_spec import SectionSpec


@dataclass(frozen=True)
class SectionMissing:
    section_id: str
    title: str
    reason: str
    stage: str

    def to_dict(self) -> dict[str, str]:
        return {
            "section_id": self.section_id,
            "title": self.title,
            "reason": self.reason,
            "stage": self.stage,
        }


@dataclass(frozen=True)
class AssemblySlot:
    section_id: str
    token: str
    title: str
    level: int
    order: int
    content: str
    missing: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "section_id": self.section_id,
            "token": self.token,
            "title": self.title,
            "level": self.level,
            "order": self.order,
            "content_chars": len(str(self.content or "").strip()),
            "missing": self.missing,
        }


@dataclass(frozen=True)
class DocumentAssemblyMap:
    title: str
    slots: list[AssemblySlot]

    def to_dict(self) -> dict[str, object]:
        return {
            "title": self.title,
            "slots": [slot.to_dict() for slot in self.slots],
        }


def build_assembly_map(*, title: str, section_specs: list[SectionSpec], content_by_id: dict[str, str]) -> DocumentAssemblyMap:
    slots: list[AssemblySlot] = []
    for spec in sorted(section_specs or [], key=lambda row: (int(row.order or 0), str(row.id or ""))):
        content = str((content_by_id or {}).get(str(spec.id or "")) or "").strip()
        slots.append(
            AssemblySlot(
                section_id=str(spec.id or ""),
                token=str(spec.token or ""),
                title=str(spec.title or ""),
                level=int(spec.level or 2),
                order=int(spec.order or 0),
                content=content,
                missing=(not content),
            )
        )
    return DocumentAssemblyMap(title=str(title or "").strip(), slots=slots)


def find_missing_sections(*, section_specs: list[SectionSpec], content_by_id: dict[str, str], stage: str) -> list[SectionMissing]:
    rows: list[SectionMissing] = []
    for spec in section_specs or []:
        content = str((content_by_id or {}).get(str(spec.id or "")) or "").strip()
        if content or str(spec.kind or "") == "reference":
            continue
        rows.append(
            SectionMissing(
                section_id=str(spec.id or ""),
                title=str(spec.title or ""),
                reason="section_content_missing",
                stage=str(stage or "assembly"),
            )
        )
    return rows


def assemble_by_id_map(*, title: str, section_specs: list[SectionSpec], content_by_id: dict[str, str]) -> tuple[str, DocumentAssemblyMap]:
    assembly_map = build_assembly_map(title=title, section_specs=section_specs, content_by_id=content_by_id)
    lines: list[str] = [f"# {title}"]
    for slot in assembly_map.slots:
        prefix = "##" if int(slot.level or 2) <= 2 else "###"
        lines.append(f"{prefix} {slot.title}")
        lines.append(str(slot.content or "").strip())
    return "\n\n".join(lines).strip() + "\n", assembly_map
