"""Validated document commands shared by the user interface and AI agents."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from .document_model import DocumentV3, iter_blocks, validate_unique_ids


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
    registry.register("replace_text", _replace_text)
    registry.register("replace_blocks", _replace_blocks)
    registry.register("insert_blocks", _insert_blocks)
    registry.register("delete_blocks", _delete_blocks)
    registry.register("move_blocks", _move_blocks)
    registry.register("add_comment", _add_comment)
    registry.register("resolve_comment", _resolve_comment)
    return registry
