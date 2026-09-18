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
        return DocumentCommand.model_json_schema()

    def execute(self, document: DocumentV3, command: DocumentCommand) -> CommandResult:
        handler = self._handlers.get(command.type)
        if handler is None:
            return CommandResult(ok=False, command_id=command.id, error="unsupported_command")
        if command.source == "ai" and command.review_mode == "suggest":
            return CommandResult(ok=False, command_id=command.id, error="review_mode_not_ready")
        working = document.model_copy(deep=True)
        try:
            changed, affected = handler(working, command)
            duplicates = validate_unique_ids(working)
            if duplicates:
                raise ValueError(f"duplicate node ids: {', '.join(duplicates)}")
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
    wanted = set(command.target.node_ids)
    if command.target.kind != "nodes" or not wanted:
        raise ValueError("command requires one or more target node ids")
    matches = [block for block in iter_blocks(document) if block.id in wanted]
    if len(matches) != len(wanted):
        found = {block.id for block in matches}
        missing = sorted(wanted - found)
        raise ValueError(f"target nodes not found: {', '.join(missing)}")
    return matches


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


def create_default_registry() -> DocumentCommandRegistry:
    registry = DocumentCommandRegistry()
    registry.register("apply_style", _apply_style)
    registry.register("set_paragraph_format", _set_paragraph_format)
    return registry

