from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field

from writing_agent.models import Citation, DraftDocument, OutlineNode, ReportRequest


@dataclass
class DocSession:
    id: str
    created_at: float = field(default_factory=time.time)
    request: ReportRequest | None = None
    outline_markdown: str = ""
    outline_tree: OutlineNode | None = None
    draft: DraftDocument | None = None
    html: str = ""
    doc_text: str = ""
    messages: list[dict[str, str]] = field(default_factory=list)  # [{"role": "...", "content": "..."}]
    template_name: str = ""
    template_html: str = ""
    template_required_h2: list[str] = field(default_factory=list)
    template_source_name: str = ""
    formatting: dict = field(default_factory=dict)
    generation_prefs: dict = field(default_factory=dict)
    uploads: dict[str, str] = field(default_factory=dict)  # file_id -> absolute path
    citations: dict[str, Citation] = field(default_factory=dict)
    citation_usage: dict[str, list[str]] = field(default_factory=dict)  # citekey -> ["Section", ...]


class InMemoryStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, DocSession] = {}

    def create(self) -> DocSession:
        session_id = uuid.uuid4().hex
        session = DocSession(id=session_id)
        with self._lock:
            self._sessions[session_id] = session
        return session

    def get(self, session_id: str) -> DocSession | None:
        with self._lock:
            return self._sessions.get(session_id)

    def put(self, session: DocSession) -> None:
        with self._lock:
            self._sessions[session.id] = session
