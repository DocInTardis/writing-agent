"""Storage module.

This module belongs to `writing_agent` in the writing-agent codebase.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

from writing_agent.models import Citation, DraftDocument, OutlineNode, ReportRequest


@dataclass
class VersionNode:
    """版本树节点"""
    version_id: str  # 唯一版本ID
    parent_id: str | None  # 父版本ID
    timestamp: float  # 创建时间戳
    message: str  # 提交信息
    author: str  # 作者（默认"user"）
    doc_text: str  # 文档快照
    doc_ir: dict  # IR快照
    tags: list[str] = field(default_factory=list)  # 标签（如"stable"）
    branch_name: str = "main"  # 分支名


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
    doc_ir: dict = field(default_factory=dict)
    messages: list[dict[str, str]] = field(default_factory=list)  # [{"role": "...", "content": "..."}]
    template_name: str = ""
    template_html: str = ""
    template_required_h2: list[str] = field(default_factory=list)
    template_outline: list[tuple[int, str]] = field(default_factory=list)
    template_source_name: str = ""
    template_source_path: str = ""
    template_source_type: str = ""
    formatting: dict = field(default_factory=dict)
    generation_prefs: dict = field(default_factory=dict)
    uploads: dict[str, str] = field(default_factory=dict)  # file_id -> absolute path
    citations: dict[str, Citation] = field(default_factory=dict)
    citation_usage: dict[str, list[str]] = field(default_factory=dict)  # citekey -> ["Section", ...]
    analysis_log: list[dict] = field(default_factory=list)
    last_analysis: dict = field(default_factory=dict)
    chat_log: list[dict] = field(default_factory=list)
    thought_log: list[dict] = field(default_factory=list)
    
    # === 版本树字段 ===
    versions: dict[str, VersionNode] = field(default_factory=dict)  # version_id -> VersionNode
    current_version_id: str | None = None  # 当前HEAD指针
    branches: dict[str, str] = field(default_factory=lambda: {"main": ""})  # branch_name -> version_id


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

    def delete(self, session_id: str) -> bool:
        with self._lock:
            return self._sessions.pop(session_id, None) is not None

    def items(self) -> list[tuple[str, DocSession]]:
        """返回所有文档的(id, session)列表"""
        with self._lock:
            return list(self._sessions.items())
