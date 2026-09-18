"""Structured document editing primitives for the third-generation editor."""

from .document_model import DocumentV3, create_document, migrate_doc_ir
from .document_commands import (
    CommandResult,
    DocumentCommand,
    DocumentCommandRegistry,
    create_default_registry,
)

__all__ = [
    "CommandResult",
    "DocumentCommand",
    "DocumentCommandRegistry",
    "DocumentV3",
    "create_default_registry",
    "create_document",
    "migrate_doc_ir",
]

