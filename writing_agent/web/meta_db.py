"""SQLite-backed metadata store for chat logs, thoughts, and feedback events.

Extracted from app_v2.py. All callers (feedback_service, document_service, etc.)
should import from here rather than reaching into app_v2 internals.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys
import time
import uuid
from pathlib import Path

from writing_agent.bounded_jsonl import append_bounded_jsonl, read_recent_jsonl

logger = logging.getLogger(__name__)

# Populated at import time by init() called from app startup.
_META_DB_PATH: Path | None = None
_LOW_SATISFACTION_PATH: Path | None = None
_DEFAULT_LOW_SATISFACTION_MAX_BYTES = 4 * 1024 * 1024


def _low_satisfaction_max_bytes() -> int:
    raw = os.environ.get("WRITING_AGENT_FEEDBACK_LOG_MAX_BYTES", str(_DEFAULT_LOW_SATISFACTION_MAX_BYTES))
    try:
        return max(64 * 1024, min(32 * 1024 * 1024, int(raw)))
    except (TypeError, ValueError):
        return _DEFAULT_LOW_SATISFACTION_MAX_BYTES


def init(meta_db_path: Path, low_satisfaction_path: Path) -> None:
    """Wire up paths. Call once during application startup."""
    global _META_DB_PATH, _LOW_SATISFACTION_PATH
    _META_DB_PATH = Path(meta_db_path).resolve()
    _LOW_SATISFACTION_PATH = Path(low_satisfaction_path).resolve()


def _default_data_dir() -> Path:
    env_value = str(os.environ.get("WRITING_AGENT_DATA_DIR", "") or "").strip()
    if env_value:
        return Path(env_value).resolve()
    app_v2 = sys.modules.get("writing_agent.web.app_v2")
    if app_v2 is not None:
        store = getattr(app_v2, "store", None)
        store_dir = getattr(store, "_persistence_dir", None)
        if isinstance(store_dir, Path):
            resolved = store_dir.resolve()
            return resolved.parent if resolved.name == "workspaces" else resolved
        data_dir = getattr(app_v2, "DATA_DIR", None)
        if isinstance(data_dir, Path):
            return data_dir.resolve()
    return Path(__file__).resolve().parents[2] / ".data"


def _preferred_paths(
    *,
    meta_db_path: Path | None = None,
    low_satisfaction_path: Path | None = None,
) -> tuple[Path, Path]:
    explicit_data_dir = bool(str(os.environ.get("WRITING_AGENT_DATA_DIR", "") or "").strip())
    app_v2 = None if explicit_data_dir else sys.modules.get("writing_agent.web.app_v2")
    runtime_meta_path = None
    runtime_low_path = None
    if app_v2 is not None:
        raw_meta_path = getattr(app_v2, "META_DB_PATH", None)
        raw_low_path = getattr(app_v2, "LOW_SATISFACTION_PATH", None)
        if raw_meta_path is not None:
            runtime_meta_path = Path(raw_meta_path).resolve()
        if raw_low_path is not None:
            runtime_low_path = Path(raw_low_path).resolve()
    data_dir = _default_data_dir()
    resolved_meta_path = Path(meta_db_path or runtime_meta_path or data_dir / "session_meta.db").resolve()
    resolved_low_path = Path(low_satisfaction_path or runtime_low_path or data_dir / "learning" / "low_satisfaction_feedback.jsonl").resolve()
    return resolved_meta_path, resolved_low_path


def ensure_initialized(
    *,
    meta_db_path: Path | None = None,
    low_satisfaction_path: Path | None = None,
) -> None:
    global _META_DB_PATH, _LOW_SATISFACTION_PATH
    resolved_meta_path, resolved_low_satisfaction_path = _preferred_paths(
        meta_db_path=meta_db_path,
        low_satisfaction_path=low_satisfaction_path,
    )
    if _META_DB_PATH == resolved_meta_path and _LOW_SATISFACTION_PATH == resolved_low_satisfaction_path:
        return
    init(
        meta_db_path=resolved_meta_path,
        low_satisfaction_path=resolved_low_satisfaction_path,
    )


def _db_path() -> Path:
    ensure_initialized()
    if _META_DB_PATH is None:
        raise RuntimeError("meta_db.init() has not been called")
    return _META_DB_PATH


def ensure_meta_db() -> None:
    ensure_initialized()
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS doc_meta (
                doc_id TEXT PRIMARY KEY,
                chat_json TEXT,
                thought_json TEXT,
                feedback_json TEXT,
                updated_at REAL
            )
            """
        )
        cols = {str(row[1]) for row in conn.execute("PRAGMA table_info(doc_meta)").fetchall()}
        if "feedback_json" not in cols:
            conn.execute("ALTER TABLE doc_meta ADD COLUMN feedback_json TEXT")
        conn.commit()
    finally:
        conn.close()


def load_meta(doc_id: str) -> dict:
    ensure_meta_db()
    conn = sqlite3.connect(_db_path())
    try:
        cur = conn.execute(
            "SELECT chat_json, thought_json, feedback_json FROM doc_meta WHERE doc_id = ?",
            (doc_id,),
        )
        row = cur.fetchone()
        if not row:
            return {"chat": [], "thoughts": [], "feedback": []}
        chat_raw, thought_raw, feedback_raw = row
        chat = json.loads(chat_raw) if chat_raw else []
        thoughts = json.loads(thought_raw) if thought_raw else []
        feedback = json.loads(feedback_raw) if feedback_raw else []
        if not isinstance(chat, list):
            chat = []
        if not isinstance(thoughts, list):
            thoughts = []
        if not isinstance(feedback, list):
            feedback = []
        return {"chat": chat, "thoughts": thoughts, "feedback": feedback}
    except (sqlite3.Error, json.JSONDecodeError) as exc:
        logger.warning("load_meta: failed to read doc_meta for %s: %s", doc_id, exc, exc_info=True)
        return {"chat": [], "thoughts": [], "feedback": []}
    finally:
        conn.close()


def save_meta(
    doc_id: str,
    *,
    chat: list | None = None,
    thoughts: list | None = None,
    feedback: list | None = None,
) -> None:
    ensure_meta_db()
    existing = load_meta(doc_id)
    chat_items = chat if chat is not None else existing.get("chat", [])
    thought_items = thoughts if thoughts is not None else existing.get("thoughts", [])
    feedback_items = feedback if feedback is not None else existing.get("feedback", [])
    conn = sqlite3.connect(_db_path())
    try:
        conn.execute(
            "INSERT INTO doc_meta(doc_id, chat_json, thought_json, feedback_json, updated_at) VALUES (?, ?, ?, ?, ?) "
            "ON CONFLICT(doc_id) DO UPDATE SET "
            "chat_json=excluded.chat_json, thought_json=excluded.thought_json, "
            "feedback_json=excluded.feedback_json, updated_at=excluded.updated_at",
            (
                doc_id,
                json.dumps(chat_items, ensure_ascii=False),
                json.dumps(thought_items, ensure_ascii=False),
                json.dumps(feedback_items, ensure_ascii=False),
                time.time(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def append_low_satisfaction_event(
    doc_id: str,
    item: dict,
    *,
    context: dict | None = None,
    doc_text: str = "",
) -> bool:
    ensure_initialized()
    if _LOW_SATISFACTION_PATH is None:
        raise RuntimeError("meta_db.init() has not been called")
    event = {
        "event_id": uuid.uuid4().hex,
        "doc_id": str(doc_id or "").strip(),
        "rating": int(item.get("rating") or 0),
        "stage": str(item.get("stage") or "general"),
        "note": str(item.get("note") or ""),
        "tags": list(item.get("tags") or []),
        "feedback_created_at": float(item.get("created_at") or time.time()),
        "recorded_at": time.time(),
        "context": dict(context or {}),
        "text_preview": str(doc_text or "").strip()[:1200],
    }
    ok = append_bounded_jsonl(
        _LOW_SATISFACTION_PATH,
        event,
        max_bytes=_low_satisfaction_max_bytes(),
    )
    if not ok:
        logger.warning("append_low_satisfaction_event: record skipped")
    return ok


def load_low_satisfaction_events(limit: int = 200) -> list[dict]:
    ensure_initialized()
    if _LOW_SATISFACTION_PATH is None:
        raise RuntimeError("meta_db.init() has not been called")
    cap = max(1, min(5000, int(limit or 200)))
    return read_recent_jsonl(
        _LOW_SATISFACTION_PATH,
        max_bytes=_low_satisfaction_max_bytes(),
        limit=cap,
    )
