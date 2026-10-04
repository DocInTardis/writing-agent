"""Validated document commands shared by the user interface and AI agents."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from .document_model import DocumentV3, StyleDefinition, iter_blocks, validate_unique_ids


class CommandTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["selection", "nodes", "section", "document"]
    node_ids: list[str] = Field(default_factory=list)
    section_id: str | None = None
    start: int | None = None
    end: int | None = None


class DocumentCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: uuid4().hex)
    type: str
    target: CommandTarget
    params: dict[str, Any] = Field(default_factory=dict)
    source: Literal["user", "shortcut", "ai", "import"] = "user"
    review_mode: Literal["direct", "suggest"] = "direct"


class CommandResult(BaseModel):
    ok: bool
    changed: bool = False
    command_id: str
    affected_node_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None
    document: DocumentV3 | None = None
    proposal: dict[str, Any] | None = None


CommandHandler = Callable[[DocumentV3, DocumentCommand], tuple[bool, list[str]]]


class DocumentCommandRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, CommandHandler] = {}

    def register(self, command_type: str, handler: CommandHandler) -> None:
        if command_type in self._handlers:
            raise ValueError(f"document command already registered: {command_type}")
        self._handlers[command_type] = handler

    def command_types(self) -> list[str]:
        return sorted(self._handlers)

    def tool_schema(self) -> dict[str, Any]:
        """JSON schema suitable for model tool/function definitions."""
        return DocumentCommand.model_json_schema(by_alias=True)

    def execute(self, document: DocumentV3, command: DocumentCommand) -> CommandResult:
        handler = self._handlers.get(command.type)
        if handler is None:
            return CommandResult(ok=False, command_id=command.id, error="unsupported_command")
        expected_version = command.params.get("expected_version")
        current_version = int(document.metadata.get("revision", 0) or 0)
        applied_ids = document.metadata.get("appliedCommandIds")
        if isinstance(applied_ids, list) and command.id in {str(value) for value in applied_ids}:
            return CommandResult(ok=True, changed=False, command_id=command.id, warnings=["duplicate_command_ignored"], document=document)
        if expected_version is not None and int(expected_version) != current_version:
            return CommandResult(ok=False, command_id=command.id, error="document_version_conflict")
        allowed = command.params.get("allowed_node_ids")
        if isinstance(allowed, list) and command.target.kind in {"nodes", "selection"}:
            outside = set(command.target.node_ids) - {str(value) for value in allowed}
            if outside:
                return CommandResult(ok=False, command_id=command.id, error="target_outside_allowed_scope")
        working = document.model_copy(deep=True)
        try:
            changed, affected = handler(working, command)
            duplicates = validate_unique_ids(working)
            if duplicates:
                raise ValueError(f"duplicate node ids: {', '.join(duplicates)}")
            if changed:
                working.metadata["revision"] = current_version + 1
            if command.source == "ai" and command.review_mode == "suggest":
                before = _snapshot_blocks(document, affected)
                after = _snapshot_blocks(working, affected)
                return CommandResult(
                    ok=True,
                    changed=False,
                    command_id=command.id,
                    affected_node_ids=affected,
                    proposal={
                        "command": command.model_dump(mode="json", by_alias=True),
                        "baseVersion": current_version,
                        "before": before,
                        "after": after,
                    },
                )
            if changed and command.source == "ai":
                ledger = working.metadata.get("appliedCommandIds")
                ledger = [str(value) for value in ledger] if isinstance(ledger, list) else []
                working.metadata["appliedCommandIds"] = [*ledger, command.id][-500:]
                working.revisions.append(
                    {
                        "id": f"revision_{uuid4().hex}",
                        "commandId": command.id,
                        "source": "ai",
                        "status": "applied",
                        "baseVersion": current_version,
                        "resultVersion": current_version + 1,
                        "affectedNodeIds": affected,
                    }
                )
            return CommandResult(
                ok=True,
                changed=changed,
                command_id=command.id,
                affected_node_ids=affected,
                document=working if changed else document,
            )
        except Exception as exc:
            return CommandResult(ok=False, command_id=command.id, error=str(exc))


def _target_blocks(document: DocumentV3, command: DocumentCommand):
    if command.target.kind == "document":
        return list(iter_blocks(document))
    if command.target.kind == "section":
        section = next((item for item in document.sections if item.id == command.target.section_id), None)
        if section is None:
            raise ValueError("target section not found")
        return list(iter_blocks(DocumentV3(sections=[section])))
    wanted = set(command.target.node_ids)
    if command.target.kind not in {"nodes", "selection"} or not wanted:
        raise ValueError("command requires one or more target node ids")
    matches = [block for block in iter_blocks(document) if block.id in wanted]
    if len(matches) != len(wanted):
        found = {block.id for block in matches}
        missing = sorted(wanted - found)
        raise ValueError(f"target nodes not found: {', '.join(missing)}")
    return matches


def _snapshot_blocks(document: DocumentV3, node_ids: list[str]) -> list[dict[str, Any]]:
    wanted = set(node_ids)
    return [
        block.model_dump(mode="json", by_alias=True)
        for block in iter_blocks(document)
        if block.id in wanted
    ]


def _target_sections(document: DocumentV3, command: DocumentCommand):
    if command.target.kind == "section":
        sections = [section for section in document.sections if section.id == command.target.section_id]
        if not sections:
            raise ValueError("target section not found")
        return sections
    if command.target.kind == "document":
        return document.sections
    if command.target.kind == "nodes":
        wanted = set(command.target.node_ids)
        def contains_target(nodes) -> bool:
            for node in nodes:
                if node.id in wanted:
                    return True
                if contains_target([child for child in node.content if hasattr(child, "id")]):
                    return True
            return False

        sections = [section for section in document.sections if contains_target(section.content)]
        if not sections:
            raise ValueError("target nodes not found")
        return sections
    raise ValueError("command target must be nodes, section, or document")


def _block_parent(document: DocumentV3, node_id: str):
    def walk(nodes):
        for index, node in enumerate(nodes):
            if not hasattr(node, "id"):
                continue
            if node.id == node_id:
                return nodes, index
            found = walk(node.content)
            if found:
                return found
        return None

    for section in document.sections:
        found = walk(section.content)
        if found:
            return found
    return None


def _apply_style(document: DocumentV3, command: DocumentCommand) -> tuple[bool, list[str]]:
    style_id = str(command.params.get("style_id") or "").strip()
    if style_id not in {style.id for style in document.styles}:
        raise ValueError(f"unknown style: {style_id}")
    styles = {style.id: style for style in document.styles}

    def resolved_properties(current_id: str, visiting: set[str] | None = None) -> dict[str, Any]:
        visiting = set(visiting or ())
        if current_id in visiting or current_id not in styles:
            return {}
        visiting.add(current_id)
        current = styles[current_id]
        inherited = resolved_properties(current.based_on, visiting) if current.based_on else {}
        own = current.properties.model_dump(by_alias=True, exclude_none=True)
        return {**inherited, **own}

    style_properties = resolved_properties(style_id)
    numbering_id = str(style_properties.get("numberingId") or "")
    numbering_level = int(style_properties.get("numberingLevel") or 0)
    changed: list[str] = []
    for block in _target_blocks(document, command):
        if block.type not in {"paragraph", "heading", "blockquote", "listItem"}:
            raise ValueError(f"style cannot be applied to {block.type}")
        if block.style_id != style_id:
            block.style_id = style_id
            if style_id.startswith("heading-"):
                block.type = "heading"
                block.attrs["level"] = int(style_id.removeprefix("heading-"))
            elif style_id == "normal" and block.type == "heading":
                block.type = "paragraph"
                block.attrs.pop("level", None)
            if numbering_id:
                block.attrs["numberingId"] = numbering_id
                block.attrs["numberingLevel"] = max(0, min(8, numbering_level))
            changed.append(block.id)
    return bool(changed), changed


def _set_paragraph_format(document: DocumentV3, command: DocumentCommand) -> tuple[bool, list[str]]:
    allowed = {
        "alignment",
        "line_spacing",
        "first_line_indent_em",
        "left_indent_em",
        "right_indent_em",
        "space_before_pt",
        "space_after_pt",
        "keep_with_next",
        "keep_lines_together",
        "page_break_before",
        "border_color",
        "border_width_pt",
        "border_style",
        "shading_color",
        "tab_stops",
        "numbering_id",
        "numbering_level",
    }
    patch = {key: deepcopy(value) for key, value in command.params.items() if key in allowed}
    if not patch:
        raise ValueError("paragraph format command has no supported parameters")
    changed: list[str] = []
    for block in _target_blocks(document, command):
        direct = block.attrs.setdefault("paragraphFormat", {})
        if not isinstance(direct, dict):
            direct = {}
            block.attrs["paragraphFormat"] = direct
        before = deepcopy(direct)
        direct.update(patch)
        if direct != before:
            changed.append(block.id)
    return bool(changed), changed


def _upsert_numbering(document: DocumentV3, command: DocumentCommand) -> tuple[bool, list[str]]:
    if command.target.kind != "document":
        raise ValueError("upsert_numbering requires a document target")
    raw = command.params.get("numbering")
    if not isinstance(raw, dict):
        raise ValueError("numbering definition is required")
    numbering_id = str(raw.get("id") or "").strip()
    name = str(raw.get("name") or "").strip()
    levels = raw.get("levels")
    if not numbering_id or not name or not isinstance(levels, list) or not levels:
        raise ValueError("numbering id, name and levels are required")
    normalized_levels: list[dict[str, Any]] = []
    seen: set[int] = set()
    formats = {"bullet", "decimal", "lowerLetter", "upperLetter", "lowerRoman", "upperRoman"}
    for raw_level in levels:
        if not isinstance(raw_level, dict):
            raise ValueError("numbering level must be an object")
        level = int(raw_level.get("level", -1))
        number_format = str(raw_level.get("format") or "")
        if level < 0 or level > 8 or level in seen or number_format not in formats:
            raise ValueError("invalid or duplicate numbering level")
        seen.add(level)
        normalized_levels.append(
            {
                "level": level,
                "format": number_format,
                "text": str(raw_level.get("text") or ("•" if number_format == "bullet" else f"%{level + 1}.")),
                "startAt": max(1, int(raw_level.get("startAt") or 1)),
                "leftIndentEm": max(0.0, float(raw_level.get("leftIndentEm") or 0)),
                "hangingIndentEm": max(0.0, float(raw_level.get("hangingIndentEm") or 0)),
                **({"bulletChar": str(raw_level.get("bulletChar") or raw_level.get("text") or "•")} if number_format == "bullet" else {}),
            }
        )
    definition = {"id": numbering_id, "name": name, "levels": sorted(normalized_levels, key=lambda item: item["level"])}
    index = next((idx for idx, item in enumerate(document.numbering) if str(item.get("id") or "") == numbering_id), -1)
    if index >= 0:
        if document.numbering[index] == definition:
            return False, []
        document.numbering[index] = definition
    else:
        document.numbering.append(definition)
    return True, []


def _apply_numbering(document: DocumentV3, command: DocumentCommand) -> tuple[bool, list[str]]:
    numbering_id = str(command.params.get("numbering_id") or "").strip()
    level = max(0, min(8, int(command.params.get("level") or 0)))
    if numbering_id not in {str(item.get("id") or "") for item in document.numbering}:
        raise ValueError(f"unknown numbering: {numbering_id}")
    changed: list[str] = []
    for block in _target_blocks(document, command):
        if block.type not in {"paragraph", "heading", "listItem", "bulletList", "orderedList"}:
            raise ValueError(f"numbering cannot be applied to {block.type}")
        before = (block.attrs.get("numberingId"), block.attrs.get("numberingLevel"))
        block.attrs["numberingId"] = numbering_id
        block.attrs["numberingLevel"] = level
        if before != (numbering_id, level):
            changed.append(block.id)
    return bool(changed), changed


def _upsert_style(document: DocumentV3, command: DocumentCommand) -> tuple[bool, list[str]]:
    if command.target.kind != "document":
        raise ValueError("upsert_style requires a document target")
    raw = command.params.get("style")
    if not isinstance(raw, dict):
        raise ValueError("style definition is required")
    definition = StyleDefinition.model_validate(raw)
    if not definition.id.strip() or not definition.name.strip():
        raise ValueError("style id and name are required")
    if definition.based_on == definition.id:
        raise ValueError("style cannot inherit itself")
    existing = {style.id: style for style in document.styles}
    prospective = {**existing, definition.id: definition}
    cursor = definition
    visited: set[str] = set()
    while cursor.based_on:
        if cursor.id in visited or cursor.based_on == definition.id:
            raise ValueError("style inheritance cycle")
        visited.add(cursor.id)
        parent = prospective.get(cursor.based_on)
        if parent is None:
            raise ValueError(f"unknown base style: {cursor.based_on}")
        cursor = parent
    if definition.next_style and definition.next_style not in prospective:
        raise ValueError(f"unknown next style: {definition.next_style}")
    index = next((i for i, style in enumerate(document.styles) if style.id == definition.id), -1)
    if index >= 0:
        if document.styles[index] == definition:
            return False, []
        document.styles[index] = definition
    else:
        document.styles.append(definition)
    return True, []


def _delete_style(document: DocumentV3, command: DocumentCommand) -> tuple[bool, list[str]]:
    if command.target.kind != "document":
        raise ValueError("delete_style requires a document target")
    style_id = str(command.params.get("style_id") or "").strip()
    protected = {"normal", "title", "subtitle", "quote", "caption", "code", *(f"heading-{level}" for level in range(1, 7))}
    if not style_id:
        raise ValueError("style_id is required")
    if style_id in protected:
        raise ValueError("built-in style cannot be deleted")
    existing = next((style for style in document.styles if style.id == style_id), None)
    if existing is None:
        raise ValueError(f"unknown style: {style_id}")
    replacement = str(command.params.get("replacement_style_id") or existing.based_on or "normal")
    if replacement == style_id or replacement not in {style.id for style in document.styles}:
        raise ValueError(f"unknown replacement style: {replacement}")
    document.styles = [style for style in document.styles if style.id != style_id]
    for style in document.styles:
        if style.based_on == style_id:
            style.based_on = replacement
        if style.next_style == style_id:
            style.next_style = replacement
    affected: list[str] = []
    for block in iter_blocks(document):
        if block.style_id == style_id:
            block.style_id = replacement
            affected.append(block.id)
    return True, affected


def _replace_text(document: DocumentV3, command: DocumentCommand) -> tuple[bool, list[str]]:
    text = str(command.params.get("text") or "")
    changed: list[str] = []
    blocks = _target_blocks(document, command)
    if command.target.kind == "selection":
        if len(blocks) != 1 or command.target.start is None or command.target.end is None:
            raise ValueError("selection replacement requires one node and start/end offsets")
        block = blocks[0]
        plain = "".join(str(child.text or "") for child in block.content if getattr(child, "type", "") == "text")
        start = max(0, min(len(plain), command.target.start))
        end = max(start, min(len(plain), command.target.end))
        text = f"{plain[:start]}{text}{plain[end:]}"
    for block in blocks:
        if block.type not in {"paragraph", "heading", "blockquote", "codeBlock"}:
            raise ValueError(f"text cannot replace {block.type}")
        from .document_model import InlineNode

        replacement = [InlineNode(type="text", text=text)] if text else []
        if block.content != replacement:
            block.content = replacement
            changed.append(block.id)
    return bool(changed), changed


def _replace_blocks(document: DocumentV3, command: DocumentCommand) -> tuple[bool, list[str]]:
    from .document_model import BlockNode

    targets = list(command.target.node_ids)
    raw_blocks = command.params.get("blocks")
    if command.target.kind != "nodes" or not targets or not isinstance(raw_blocks, list):
        raise ValueError("replace_blocks requires node targets and blocks")
    replacements = [BlockNode.model_validate(item) for item in raw_blocks]
    if len(set(targets)) != len(targets):
        raise ValueError("duplicate target node ids")
    first = _block_parent(document, targets[0])
    if first is None:
        raise ValueError("target node not found")
    parent, start = first
    indexes = []
    for target in targets:
        found = _block_parent(document, target)
        if found is None or found[0] is not parent:
            raise ValueError("replacement targets must share one parent")
        indexes.append(found[1])
    if indexes != list(range(min(indexes), max(indexes) + 1)):
        raise ValueError("replacement targets must be contiguous")
    parent[min(indexes): max(indexes) + 1] = replacements
    return True, [block.id for block in replacements]


def _insert_blocks(document: DocumentV3, command: DocumentCommand) -> tuple[bool, list[str]]:
    from .document_model import BlockNode

    raw_blocks = command.params.get("blocks")
    if not isinstance(raw_blocks, list) or not raw_blocks:
        raise ValueError("insert_blocks requires blocks")
    blocks = [BlockNode.model_validate(item) for item in raw_blocks]
    if command.target.kind == "nodes":
        if len(command.target.node_ids) != 1:
            raise ValueError("insert_blocks node target must contain exactly one anchor")
        found = _block_parent(document, command.target.node_ids[0])
        if found is None:
            raise ValueError("anchor node not found")
        parent, index = found
        if command.params.get("placement") != "before":
            index += 1
        parent[index:index] = blocks
    else:
        sections = _target_sections(document, command)
        if len(sections) != 1:
            raise ValueError("insert_blocks requires exactly one section")
        sections[0].content.extend(blocks)
    return True, [block.id for block in blocks]


def _delete_blocks(document: DocumentV3, command: DocumentCommand) -> tuple[bool, list[str]]:
    targets = list(command.target.node_ids)
    if command.target.kind != "nodes" or not targets:
        raise ValueError("delete_blocks requires node targets")
    for target in targets:
        found = _block_parent(document, target)
        if found is None:
            raise ValueError(f"target node not found: {target}")
        parent, index = found
        parent.pop(index)
    return True, targets


def _move_blocks(document: DocumentV3, command: DocumentCommand) -> tuple[bool, list[str]]:
    targets = list(command.target.node_ids)
    anchor = str(command.params.get("anchor_id") or "")
    placement = str(command.params.get("placement") or "before")
    if command.target.kind != "nodes" or not targets or not anchor or anchor in targets:
        raise ValueError("move_blocks requires node targets and another anchor")
    located = [_block_parent(document, target) for target in targets]
    if any(item is None for item in located):
        raise ValueError("move target not found")
    parents = [item[0] for item in located if item]
    if any(parent is not parents[0] for parent in parents):
        raise ValueError("move targets must share one parent")
    source = parents[0]
    indexes = [item[1] for item in located if item]
    if sorted(indexes) != list(range(min(indexes), max(indexes) + 1)):
        raise ValueError("move targets must be contiguous")
    moving = source[min(indexes):max(indexes) + 1]
    del source[min(indexes):max(indexes) + 1]
    anchor_found = _block_parent(document, anchor)
    if anchor_found is None:
        raise ValueError("move anchor not found")
    parent, index = anchor_found
    if placement == "after":
        index += 1
    parent[index:index] = moving
    return True, targets


def _add_comment(document: DocumentV3, command: DocumentCommand) -> tuple[bool, list[str]]:
    targets = [block.id for block in _target_blocks(document, command)]
    text = str(command.params.get("text") or "").strip()
    if not text:
        raise ValueError("comment text is required")
    document.comments.append(
        {
            "id": f"comment_{uuid4().hex}",
            "nodeIds": targets,
            "start": command.target.start,
            "end": command.target.end,
            "text": text,
            "author": str(command.params.get("author") or "用户"),
            "resolved": False,
        }
    )
    return True, targets


def _resolve_comment(document: DocumentV3, command: DocumentCommand) -> tuple[bool, list[str]]:
    comment_id = str(command.params.get("comment_id") or "")
    for comment in document.comments:
        if str(comment.get("id")) == comment_id:
            comment["resolved"] = bool(command.params.get("resolved", True))
            return True, [str(value) for value in comment.get("nodeIds") or []]
    raise ValueError("comment not found")


def create_default_registry() -> DocumentCommandRegistry:
    registry = DocumentCommandRegistry()
    registry.register("apply_style", _apply_style)
    registry.register("set_paragraph_format", _set_paragraph_format)
    registry.register("upsert_style", _upsert_style)
    registry.register("delete_style", _delete_style)
    registry.register("upsert_numbering", _upsert_numbering)
    registry.register("apply_numbering", _apply_numbering)
    registry.register("replace_text", _replace_text)
    registry.register("replace_blocks", _replace_blocks)
    registry.register("insert_blocks", _insert_blocks)
    registry.register("delete_blocks", _delete_blocks)
    registry.register("move_blocks", _move_blocks)
    registry.register("add_comment", _add_comment)
    registry.register("resolve_comment", _resolve_comment)
    return registry
