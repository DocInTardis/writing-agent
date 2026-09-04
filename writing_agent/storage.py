"""Storage module.

This module belongs to `writing_agent` in the writing-agent codebase.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import threading
import time
import uuid
from collections import OrderedDict
from copy import copy
from dataclasses import asdict, dataclass, field, is_dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

from writing_agent.models import (
    Citation,
    CitationStyle,
    DraftDocument,
    FormattingRequirements,
    OutlineNode,
    Paragraph,
    ReportRequest,
    SectionDraft,
)


@dataclass
class VersionNode:
    """Version tree node."""

    version_id: str
    parent_id: str | None
    timestamp: float
    message: str
    author: str
    doc_text: str
    doc_ir: dict
    tags: list[str] = field(default_factory=list)
    branch_name: str = "main"


@dataclass
class DocSession:
    id: str
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    last_opened_at: float = field(default_factory=time.time)
    title: str = ""
    title_locked: bool = False
    pinned: bool = False
    status: str = "draft"
    labels: list[str] = field(default_factory=list)
    owner: str = ""
    priority: str = ""
    due_at: float = 0.0
    archived: bool = False
    trashed: bool = False
    trash_until: float = 0.0
    request: ReportRequest | None = None
    outline_markdown: str = ""
    outline_tree: OutlineNode | None = None
    draft: DraftDocument | None = None
    html: str = ""
    doc_text: str = ""
    doc_ir: dict = field(default_factory=dict)
    messages: list[dict[str, str]] = field(default_factory=list)
    template_name: str = ""
    template_html: str = ""
    template_required_h2: list[str] = field(default_factory=list)
    template_outline: list[tuple[int, str]] = field(default_factory=list)
    template_source_name: str = ""
    template_source_path: str = ""
    template_source_type: str = ""
    formatting: dict = field(default_factory=dict)
    generation_prefs: dict = field(default_factory=dict)
    uploads: dict[str, str] = field(default_factory=dict)
    citations: dict[str, Citation] = field(default_factory=dict)
    citation_usage: dict[str, list[str]] = field(default_factory=dict)
    activity_log: list[dict] = field(default_factory=list)
    analysis_log: list[dict] = field(default_factory=list)
    last_analysis: dict = field(default_factory=dict)
    chat_log: list[dict] = field(default_factory=list)
    thought_log: list[dict] = field(default_factory=list)
    versions: dict[str, VersionNode] = field(default_factory=dict)
    current_version_id: str | None = None
    branches: dict[str, str] = field(default_factory=lambda: {"main": ""})


def _coerce_int(value: object, default: int) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _coerce_float(value: object, default: float) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _coerce_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "on"}


def _normalize_labels(value: object, *, limit: int = 12, max_length: int = 32) -> list[str]:
    if isinstance(value, str):
        raw_items = re.split(r"[,;\n]+", value)
    elif isinstance(value, (list, tuple, set)):
        raw_items = list(value)
    else:
        raw_items = []
    labels: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        label = " ".join(str(item or "").replace("#", " ").split()).strip()[:max_length]
        if not label:
            continue
        label_key = label.casefold()
        if label_key in seen:
            continue
        seen.add(label_key)
        labels.append(label)
        if len(labels) >= limit:
            break
    return labels


def _normalize_owner(value: object, *, max_length: int = 48) -> str:
    return " ".join(str(value or "").split()).strip()[:max_length]


def _normalize_priority(value: object) -> str:
    priority = str(value or "").strip().lower()
    return priority if priority in {"", "low", "medium", "high", "urgent"} else ""


def _normalize_due_at(value: object) -> float:
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        try:
            numeric = float(value)
        except Exception:
            return 0.0
        return numeric if numeric > 0 else 0.0
    text = str(value or "").strip()
    if not text:
        return 0.0
    try:
        numeric = float(text)
    except Exception:
        numeric = 0.0
    if numeric > 0:
        return numeric
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        try:
            return time.mktime(time.strptime(f"{text} 23:59:59", "%Y-%m-%d %H:%M:%S"))
        except Exception:
            return 0.0
    return 0.0


def _derive_session_title(session: DocSession) -> str:
    explicit = str(getattr(session, "title", "") or "").strip()
    if bool(getattr(session, "title_locked", False)) and explicit:
        return explicit[:200]
    if explicit and explicit not in {"未命名文档", "Untitled"} and not str(getattr(session, "doc_text", "") or "").strip():
        return explicit[:200]
    request = getattr(session, "request", None)
    topic = str(getattr(request, "topic", "") or "").strip()
    if topic:
        return topic[:200]
    text = str(getattr(session, "doc_text", "") or "")
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            candidate = re.sub(r"^#+\s*", "", stripped).strip()
            if candidate:
                return candidate[:200]
    return "未命名文档"


def _restore_outline_node(raw: object) -> OutlineNode | None:
    if not isinstance(raw, dict):
        return None
    children = [node for item in raw.get("children", []) if (node := _restore_outline_node(item)) is not None]
    notes = [str(item) for item in raw.get("notes", []) if str(item or "").strip()]
    return OutlineNode(
        title=str(raw.get("title") or "").strip(),
        level=_coerce_int(raw.get("level"), 1),
        notes=notes,
        children=children,
    )


def _restore_draft_document(raw: object) -> DraftDocument | None:
    if not isinstance(raw, dict):
        return None
    sections: list[SectionDraft] = []
    for section in raw.get("sections", []):
        if not isinstance(section, dict):
            continue
        paragraphs = [
            Paragraph(text=str(item.get("text") or ""))
            for item in section.get("paragraphs", [])
            if isinstance(item, dict)
        ]
        sections.append(
            SectionDraft(
                title=str(section.get("title") or ""),
                level=_coerce_int(section.get("level"), 1),
                paragraphs=paragraphs,
            )
        )
    return DraftDocument(title=str(raw.get("title") or ""), sections=sections)


def _restore_request(raw: object) -> ReportRequest | None:
    if not isinstance(raw, dict):
        return None
    formatting_raw = raw.get("formatting") if isinstance(raw.get("formatting"), dict) else {}
    citation_style_raw = str(formatting_raw.get("citation_style") or CitationStyle.GBT)
    try:
        citation_style = CitationStyle(citation_style_raw)
    except ValueError:
        logger.warning("Unknown citation style %r, falling back to GBT", citation_style_raw)
        citation_style = CitationStyle.GBT
    formatting = FormattingRequirements(
        word_count=_coerce_int(formatting_raw.get("word_count"), 0) or None,
        heading_levels=_coerce_int(formatting_raw.get("heading_levels"), 3),
        citation_style=citation_style,
        font_name=str(formatting_raw.get("font_name") or FormattingRequirements.font_name),
        font_name_east_asia=str(
            formatting_raw.get("font_name_east_asia") or FormattingRequirements.font_name_east_asia
        ),
        font_size_pt=_coerce_float(formatting_raw.get("font_size_pt"), FormattingRequirements.font_size_pt),
        line_spacing=_coerce_float(formatting_raw.get("line_spacing"), FormattingRequirements.line_spacing),
        heading1_font_name=str(formatting_raw.get("heading1_font_name") or FormattingRequirements.heading1_font_name),
        heading1_font_name_east_asia=str(
            formatting_raw.get("heading1_font_name_east_asia") or FormattingRequirements.heading1_font_name_east_asia
        ),
        heading1_size_pt=_coerce_float(formatting_raw.get("heading1_size_pt"), FormattingRequirements.heading1_size_pt or 22),
        heading2_font_name=str(formatting_raw.get("heading2_font_name") or FormattingRequirements.heading2_font_name),
        heading2_font_name_east_asia=str(
            formatting_raw.get("heading2_font_name_east_asia") or FormattingRequirements.heading2_font_name_east_asia
        ),
        heading2_size_pt=_coerce_float(formatting_raw.get("heading2_size_pt"), FormattingRequirements.heading2_size_pt or 16),
        heading3_font_name=str(formatting_raw.get("heading3_font_name") or FormattingRequirements.heading3_font_name),
        heading3_font_name_east_asia=str(
            formatting_raw.get("heading3_font_name_east_asia") or FormattingRequirements.heading3_font_name_east_asia
        ),
        heading3_size_pt=_coerce_float(formatting_raw.get("heading3_size_pt"), FormattingRequirements.heading3_size_pt or 16),
    )
    return ReportRequest(
        topic=str(raw.get("topic") or ""),
        report_type=str(raw.get("report_type") or ""),
        formatting=formatting,
        include_figures=_coerce_bool(raw.get("include_figures")),
        writing_style=str(raw.get("writing_style") or ""),
        manual_sources_text=str(raw.get("manual_sources_text") or ""),
    )


def _restore_citations(raw: object) -> dict[str, Citation]:
    if not isinstance(raw, dict):
        return {}
    citations: dict[str, Citation] = {}
    for key, item in raw.items():
        if not isinstance(item, dict):
            continue
        cite_key = str(item.get("key") or key or "").strip()
        if not cite_key:
            continue
        citations[cite_key] = Citation(
            key=cite_key,
            title=str(item.get("title") or ""),
            url=str(item.get("url") or "") or None,
            authors=str(item.get("authors") or "") or None,
            year=str(item.get("year") or "") or None,
            venue=str(item.get("venue") or "") or None,
        )
    return citations


def _restore_versions(raw: object) -> dict[str, VersionNode]:
    if not isinstance(raw, dict):
        return {}
    versions: dict[str, VersionNode] = {}
    for key, item in raw.items():
        if not isinstance(item, dict):
            continue
        version_id = str(item.get("version_id") or key or "").strip()
        if not version_id:
            continue
        versions[version_id] = VersionNode(
            version_id=version_id,
            parent_id=str(item.get("parent_id") or "") or None,
            timestamp=_coerce_float(item.get("timestamp"), time.time()),
            message=str(item.get("message") or ""),
            author=str(item.get("author") or "user"),
            doc_text=str(item.get("doc_text") or ""),
            doc_ir=dict(item.get("doc_ir") or {}),
            tags=[str(tag) for tag in item.get("tags", []) if str(tag or "").strip()],
            branch_name=str(item.get("branch_name") or "main"),
        )
    return versions


def _restore_session(raw: dict, session_id: str) -> DocSession:
    now = time.time()
    session = DocSession(id=str(raw.get("id") or session_id or uuid.uuid4().hex))
    session.created_at = _coerce_float(raw.get("created_at"), now)
    session.updated_at = _coerce_float(raw.get("updated_at"), session.created_at)
    session.last_opened_at = _coerce_float(raw.get("last_opened_at"), session.updated_at)
    session.title = str(raw.get("title") or "")
    session.title_locked = _coerce_bool(raw.get("title_locked"))
    session.pinned = _coerce_bool(raw.get("pinned"))
    session.status = str(raw.get("status") or "draft") or "draft"
    session.labels = _normalize_labels(raw.get("labels"))
    session.owner = _normalize_owner(raw.get("owner"))
    session.priority = _normalize_priority(raw.get("priority"))
    session.due_at = _normalize_due_at(raw.get("due_at"))
    session.archived = _coerce_bool(raw.get("archived"))
    session.trashed = _coerce_bool(raw.get("trashed"))
    session.trash_until = _coerce_float(raw.get("trash_until"), 0.0)
    session.request = _restore_request(raw.get("request"))
    session.outline_markdown = str(raw.get("outline_markdown") or "")
    session.outline_tree = _restore_outline_node(raw.get("outline_tree"))
    session.draft = _restore_draft_document(raw.get("draft"))
    session.html = str(raw.get("html") or "")
    session.doc_text = str(raw.get("doc_text") or "")
    session.doc_ir = dict(raw.get("doc_ir") or {})
    session.messages = list(raw.get("messages") or [])
    session.template_name = str(raw.get("template_name") or "")
    session.template_html = str(raw.get("template_html") or "")
    session.template_required_h2 = [str(item) for item in raw.get("template_required_h2", [])]
    session.template_outline = [
        (_coerce_int(item[0], 1), str(item[1]))
        for item in raw.get("template_outline", [])
        if isinstance(item, (list, tuple)) and len(item) >= 2
    ]
    session.template_source_name = str(raw.get("template_source_name") or "")
    session.template_source_path = str(raw.get("template_source_path") or "")
    session.template_source_type = str(raw.get("template_source_type") or "")
    session.formatting = dict(raw.get("formatting") or {})
    session.generation_prefs = dict(raw.get("generation_prefs") or {})
    session.uploads = {str(key): str(value) for key, value in dict(raw.get("uploads") or {}).items()}
    session.citations = _restore_citations(raw.get("citations"))
    session.citation_usage = {
        str(key): [str(item) for item in value]
        for key, value in dict(raw.get("citation_usage") or {}).items()
        if isinstance(value, list)
    }
    session.activity_log = list(raw.get("activity_log") or [])
    session.analysis_log = list(raw.get("analysis_log") or [])
    session.last_analysis = dict(raw.get("last_analysis") or {})
    session.chat_log = list(raw.get("chat_log") or [])
    session.thought_log = list(raw.get("thought_log") or [])
    session.versions = _restore_versions(raw.get("versions"))
    session.current_version_id = str(raw.get("current_version_id") or "") or None
    session.branches = {str(key): str(value) for key, value in dict(raw.get("branches") or {"main": ""}).items()}
    session.title = _derive_session_title(session)
    if session.trashed:
        session.trash_until = _coerce_float(session.trash_until, 0.0)
    else:
        session.trash_until = 0.0
    if session.archived:
        session.status = "archived"
    return session


# Maximum number of sessions held in memory at once. Oldest-accessed sessions
# beyond this limit are evicted from RAM (but remain on disk if persistence is
# enabled).  Override via WRITING_AGENT_STORE_MAX_SESSIONS env var.
_DEFAULT_MAX_SESSIONS = 500


class InMemoryStore:
    def __init__(
        self,
        persistence_dir: str | Path | None = None,
        max_sessions: int | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._sessions: OrderedDict[str, DocSession] = OrderedDict()
        self._persistence_dir = Path(persistence_dir).resolve() if persistence_dir else None
        try:
            env_max = int(str(os.environ.get("WRITING_AGENT_STORE_MAX_SESSIONS", "") or ""))
            self._max_sessions = max(1, env_max)
        except (ValueError, TypeError):
            self._max_sessions = max(1, int(max_sessions or _DEFAULT_MAX_SESSIONS))
        if self._persistence_dir is not None:
            self._persistence_dir.mkdir(parents=True, exist_ok=True)
            self._load_persisted_sessions()

    def _session_path(self, session_id: str) -> Path:
        if self._persistence_dir is None:
            raise RuntimeError("persistence is not enabled")
        return self._persistence_dir / f"{session_id}.json"

    def _evict_if_needed(self) -> None:
        """Evict least-recently-used sessions when the in-memory limit is exceeded."""
        while len(self._sessions) > self._max_sessions:
            evicted_id, _ = self._sessions.popitem(last=False)
            logger.debug("InMemoryStore: evicted session %s from memory (limit=%d)", evicted_id, self._max_sessions)

    def _normalize_session(self, session: DocSession, *, touch_updated: bool) -> DocSession:
        now = time.time()
        if not getattr(session, "created_at", 0.0):
            session.created_at = now
        session.updated_at = now if touch_updated else _coerce_float(getattr(session, "updated_at", now), now)
        if not getattr(session, "last_opened_at", 0.0):
            session.last_opened_at = session.updated_at
        session.title = _derive_session_title(session)
        session.archived = bool(getattr(session, "archived", False))
        session.trashed = bool(getattr(session, "trashed", False))
        session.pinned = bool(getattr(session, "pinned", False))
        session.labels = _normalize_labels(getattr(session, "labels", []))
        session.owner = _normalize_owner(getattr(session, "owner", ""))
        session.priority = _normalize_priority(getattr(session, "priority", ""))
        session.due_at = _normalize_due_at(getattr(session, "due_at", 0.0))
        session.trash_until = _coerce_float(getattr(session, "trash_until", 0.0), 0.0) if session.trashed else 0.0
        status = str(getattr(session, "status", "draft") or "draft")
        session.status = "archived" if session.archived and not session.trashed else status
        return session

    def _persist_session(self, session: DocSession) -> None:
        if self._persistence_dir is None:
            return
        payload = asdict(session)
        payload["schema_version"] = 1
        path = self._session_path(session.id)
        serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=self._json_default)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=path.parent,
                prefix=path.name + ".", suffix=".tmp", delete=False,
            ) as stream:
                temp_path = Path(stream.name)
                stream.write(serialized)
            self._replace_session_file(temp_path, path)
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    logger.warning("Could not remove session temporary file %s", temp_path)

    @staticmethod
    def _replace_session_file(temp_path: Path, path: Path) -> None:
        """Replace a persisted session file, tolerating brief Windows file locks."""

        last_error: PermissionError | None = None
        for attempt in range(8):
            try:
                temp_path.replace(path)
                return
            except PermissionError as exc:
                last_error = exc
                time.sleep(0.025 * (attempt + 1))
        if last_error is not None:
            raise last_error

    @staticmethod
    def _json_default(value: object):
        if is_dataclass(value):
            return asdict(value)
        if hasattr(value, "model_dump"):
            try:
                return value.model_dump()
            except Exception as _exc:
                logger.debug("Ignored error in storage.py: %s", _exc, exc_info=True)

        if hasattr(value, "dict"):
            try:
                return value.dict()
            except Exception as _exc:
                logger.debug("Ignored error in storage.py: %s", _exc, exc_info=True)

        if hasattr(value, "__dict__"):
            try:
                return dict(value.__dict__)
            except Exception as _exc:
                logger.debug("Ignored error in storage.py: %s", _exc, exc_info=True)

        return str(value)

    def _load_persisted_sessions(self) -> None:
        if self._persistence_dir is None:
            return
        for path in sorted(self._persistence_dir.glob("*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                logger.warning("InMemoryStore: skipping unreadable session file %s: %s", path, exc)
                continue
            if not isinstance(raw, dict):
                continue
            try:
                session = _restore_session(raw, path.stem)
            except Exception as exc:
                logger.warning("InMemoryStore: failed to restore session %s: %s", path.stem, exc)
                continue
            self._sessions[session.id] = self._normalize_session(session, touch_updated=False)

    def touch(self, session_id: str) -> DocSession | None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None
            candidate = copy(session)
            candidate.last_opened_at = time.time()
            candidate = self._normalize_session(candidate, touch_updated=False)
            self._persist_session(candidate)
            session.__dict__.update(candidate.__dict__)
            # Move to end to mark as most-recently-used
            self._sessions.move_to_end(session_id)
            self._sessions[session_id] = session
            return session

    def create(self) -> DocSession:
        session_id = uuid.uuid4().hex
        session = DocSession(id=session_id)
        with self._lock:
            session = self._normalize_session(session, touch_updated=True)
            self._persist_session(session)
            self._sessions[session_id] = session
            self._evict_if_needed()
        return session

    def get(self, session_id: str) -> DocSession | None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is not None:
                self._sessions.move_to_end(session_id)
            return session

    def put(self, session: DocSession) -> None:
        with self._lock:
            candidate = self._normalize_session(copy(session), touch_updated=True)
            self._persist_session(candidate)
            session.__dict__.update(candidate.__dict__)
            self._sessions[session.id] = session
            self._sessions.move_to_end(session.id)
            self._evict_if_needed()

    def delete(self, session_id: str) -> bool:
        with self._lock:
            deleted = session_id in self._sessions
            if deleted and self._persistence_dir is not None:
                try:
                    self._session_path(session_id).unlink()
                except FileNotFoundError:
                    pass
            if deleted:
                self._sessions.pop(session_id)
            return deleted

    def items(self) -> list[tuple[str, DocSession]]:
        with self._lock:
            return list(self._sessions.items())
