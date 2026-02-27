"""Locking module.

This module belongs to `writing_agent.state_engine` in the writing-agent codebase.
"""

from __future__ import annotations

from dataclasses import dataclass
import threading
import time
import uuid


@dataclass
class LockRecord:
    lock_id: str
    owner: str
    scope_type: str
    target_ids: set[str]
    expires_at: float

    def to_view(self) -> dict:
        return {
            "lock_id": self.lock_id,
            "scope_type": self.scope_type,
            "target_ids": sorted(self.target_ids),
            "owner": self.owner,
            "expires_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.expires_at)),
        }


class DocLockManager:
    def __init__(self) -> None:
        self._mu = threading.Lock()
        self._global: dict[str, LockRecord] = {}
        self._partial: dict[str, list[LockRecord]] = {}

    def _cleanup_expired(self, doc_id: str) -> None:
        now = time.time()
        g = self._global.get(doc_id)
        if g and g.expires_at <= now:
            self._global.pop(doc_id, None)
        parts = self._partial.get(doc_id) or []
        parts = [p for p in parts if p.expires_at > now]
        if parts:
            self._partial[doc_id] = parts
        else:
            self._partial.pop(doc_id, None)

    def acquire_global(self, doc_id: str, owner: str, *, ttl_s: int = 600) -> tuple[bool, str | None]:
        with self._mu:
            self._cleanup_expired(doc_id)
            g = self._global.get(doc_id)
            if g and g.owner != owner:
                return False, "global lock occupied"
            parts = self._partial.get(doc_id) or []
            if any(p.owner != owner for p in parts):
                return False, "partial lock occupied"
            self._global[doc_id] = LockRecord(
                lock_id=uuid.uuid4().hex,
                owner=owner,
                scope_type="doc",
                target_ids=set(),
                expires_at=time.time() + max(1, ttl_s),
            )
            return True, None

    def acquire_partial(
        self,
        doc_id: str,
        owner: str,
        *,
        scope_type: str,
        target_ids: list[str],
        ttl_s: int = 600,
    ) -> tuple[bool, str | None]:
        wanted = {str(x).strip() for x in (target_ids or []) if str(x).strip()}
        if not wanted:
            return False, "empty target ids"
        with self._mu:
            self._cleanup_expired(doc_id)
            g = self._global.get(doc_id)
            if g and g.owner != owner:
                return False, "global lock occupied"
            existing = self._partial.get(doc_id) or []
            for rec in existing:
                if rec.owner == owner:
                    continue
                if rec.target_ids.intersection(wanted):
                    return False, "partial lock conflict"
            rec = LockRecord(
                lock_id=uuid.uuid4().hex,
                owner=owner,
                scope_type=scope_type,
                target_ids=wanted,
                expires_at=time.time() + max(1, ttl_s),
            )
            self._partial.setdefault(doc_id, []).append(rec)
            return True, None

    def resolve_conflict(self, doc_id: str, owner: str, target_ids: list[str]) -> tuple[str, str | None]:
        wanted = {str(x).strip() for x in (target_ids or []) if str(x).strip()}
        with self._mu:
            self._cleanup_expired(doc_id)
            g = self._global.get(doc_id)
            if g and g.owner != owner:
                return "conflict", "global lock occupied"
            if not wanted:
                return "conflict", "empty target ids"
            for rec in self._partial.get(doc_id) or []:
                if rec.owner == owner:
                    continue
                if rec.target_ids.intersection(wanted):
                    return "conflict", "partial lock conflict"
            return "success", None

    def release_owner(self, doc_id: str, owner: str) -> None:
        with self._mu:
            g = self._global.get(doc_id)
            if g and g.owner == owner:
                self._global.pop(doc_id, None)
            parts = self._partial.get(doc_id) or []
            parts = [p for p in parts if p.owner != owner]
            if parts:
                self._partial[doc_id] = parts
            else:
                self._partial.pop(doc_id, None)

    def list_locks(self, doc_id: str) -> dict:
        with self._mu:
            self._cleanup_expired(doc_id)
            g = self._global.get(doc_id)
            parts = self._partial.get(doc_id) or []
            return {
                "global_lock": bool(g),
                "partial_locks": [p.to_view() for p in parts],
            }

