"""Section specification primitives for stable section identity."""

from __future__ import annotations

import re
from dataclasses import dataclass


_SECTION_TOKEN_RE = re.compile(r"^H([23])::(.*)$")


@dataclass(frozen=True)
class SectionSpec:
    id: str
    token: str
    title: str
    level: int
    order: int
    parent_id: str = ""
    kind: str = "content"

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "token": self.token,
            "title": self.title,
            "level": self.level,
            "order": self.order,
            "parent_id": self.parent_id,
            "kind": self.kind,
        }


def split_section_token(section: str) -> tuple[int, str]:
    raw = str(section or "").strip()
    if not raw:
        return 2, ""
    match = _SECTION_TOKEN_RE.match(raw)
    if match:
        try:
            level = int(match.group(1))
        except Exception:
            level = 2
        title = str(match.group(2) or "").strip()
        return (3 if level >= 3 else 2), title
    return 2, raw


def encode_section_token(level: int, title: str) -> str:
    normalized_level = 3 if int(level or 2) >= 3 else 2
    return f"H{normalized_level}::{str(title or '').strip()}"


def is_reference_title(title: str) -> bool:
    lowered = str(title or "").strip().lower()
    if not lowered:
        return False
    return ("参考文献" in lowered) or ("参考资料" in lowered) or ("references" in lowered) or (lowered == "文献")


def build_section_specs(sections: list[str]) -> list[SectionSpec]:
    specs: list[SectionSpec] = []
    parent_h2_id = ""
    for idx, raw in enumerate(sections or [], start=1):
        level, title = split_section_token(raw)
        if not title:
            continue
        token = encode_section_token(level, title)
        sec_id = f"sec_{idx:03d}"
        if level <= 2:
            parent_id = ""
            parent_h2_id = sec_id
        else:
            parent_id = parent_h2_id
        kind = "reference" if is_reference_title(title) else "content"
        specs.append(
            SectionSpec(
                id=sec_id,
                token=token,
                title=title,
                level=level,
                order=idx,
                parent_id=parent_id,
                kind=kind,
            )
        )
    return specs


def token_to_id_map(specs: list[SectionSpec]) -> dict[str, str]:
    out: dict[str, str] = {}
    for spec in specs or []:
        if not isinstance(spec, SectionSpec):
            continue
        token = str(spec.token or "").strip()
        sid = str(spec.id or "").strip()
        if token and sid:
            out[token] = sid
    return out

