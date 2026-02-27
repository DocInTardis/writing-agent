"""Generation Lock module.

This module belongs to `writing_agent.web` in the writing-agent codebase.
"""

from __future__ import annotations

import os
import threading
import time
import uuid


class DocGenerationState:
    """In-memory generation lock state scoped to doc id."""

    def __init__(
        self,
        *,
        stale_after_s: float | None = None,
        max_age_s: float | None = None,
        time_fn=None,
    ) -> None:
        self._lock = threading.Lock()
        self._state: dict[str, dict] = {}
        self._time_fn = time_fn or time.time
        self._stale_after_s = self._resolve_window(stale_after_s, "WRITING_AGENT_DOC_LOCK_STALE_S", 180.0)
        self._max_age_s = self._resolve_window(max_age_s, "WRITING_AGENT_DOC_LOCK_MAX_AGE_S", 1800.0)

    @staticmethod
    def _resolve_window(value: float | None, env_name: str, default: float) -> float:
        if value is not None:
            try:
                return max(0.0, float(value))
            except Exception:
                return float(default)
        raw = str(os.environ.get(env_name, "")).strip()
        if not raw:
            return float(default)
        try:
            return max(0.0, float(raw))
        except Exception:
            return float(default)

    def _now(self) -> float:
        return float(self._time_fn())

    def _is_expired(self, cur: dict, *, now: float) -> bool:
        started_at = float(cur.get("started_at") or 0.0)
        last_touch_at = float(cur.get("last_touch_at") or started_at or 0.0)
        idle_s = max(0.0, now - last_touch_at)
        age_s = max(0.0, now - started_at) if started_at > 0 else idle_s
        if self._stale_after_s > 0 and idle_s >= self._stale_after_s:
            return True
        if self._max_age_s > 0 and age_s >= self._max_age_s:
            return True
        return False

    def try_begin(self, doc_id: str, *, mode: str, target_ids: list[str] | None = None) -> str | None:
        token = uuid.uuid4().hex
        now = self._now()
        with self._lock:
            cur = self._state.get(doc_id)
            if isinstance(cur, dict):
                if self._is_expired(cur, now=now):
                    self._state.pop(doc_id, None)
                else:
                    return None
            self._state[doc_id] = {
                "token": token,
                "mode": str(mode or "generate"),
                "started_at": now,
                "last_touch_at": now,
                "target_ids": list(target_ids or []),
            }
        return token

    def begin_with_wait(
        self,
        doc_id: str,
        *,
        mode: str,
        target_ids: list[str] | None = None,
        wait_s: float = 0.0,
        poll_s: float = 0.1,
    ) -> str | None:
        """Try to acquire the doc lock for a bounded time window."""
        wait_budget = max(0.0, float(wait_s or 0.0))
        interval = max(0.01, float(poll_s or 0.1))
        token = self.try_begin(doc_id, mode=mode, target_ids=target_ids)
        if token or wait_budget <= 0:
            return token

        deadline = self._now() + wait_budget
        while self._now() < deadline:
            remain = max(0.0, deadline - self._now())
            time.sleep(min(interval, remain))
            token = self.try_begin(doc_id, mode=mode, target_ids=target_ids)
            if token:
                return token
        return None

    def touch(self, doc_id: str, token: str | None = None) -> bool:
        now = self._now()
        with self._lock:
            cur = self._state.get(doc_id)
            if not isinstance(cur, dict):
                return False
            if token and str(cur.get("token") or "") != str(token):
                return False
            cur["last_touch_at"] = now
            return True

    def finish(self, doc_id: str, token: str | None) -> None:
        if not token:
            return
        with self._lock:
            cur = self._state.get(doc_id)
            if not isinstance(cur, dict):
                return
            if str(cur.get("token") or "") != str(token):
                return
            self._state.pop(doc_id, None)

    def busy_message(self, doc_id: str) -> str:
        now = self._now()
        with self._lock:
            cur = self._state.get(doc_id)
        if not isinstance(cur, dict):
            return "当前文档暂时不可编辑，请稍后重试。"
        if self._is_expired(cur, now=now):
            with self._lock:
                latest = self._state.get(doc_id)
                if isinstance(latest, dict) and self._is_expired(latest, now=now):
                    self._state.pop(doc_id, None)
            return "当前文档暂时不可编辑，请稍后重试。"
        mode = str(cur.get("mode") or "generate")
        started_at = float(cur.get("started_at") or 0.0)
        last_touch_at = float(cur.get("last_touch_at") or started_at or 0.0)
        elapsed = max(0, int(now - started_at)) if started_at > 0 else 0
        idle = max(0, int(now - last_touch_at)) if last_touch_at > 0 else 0
        return f"当前文档正在执行 {mode}（约 {elapsed}s，最近活动约 {idle}s 前），请稍后重试。"

    def is_busy(self, doc_id: str) -> bool:
        now = self._now()
        with self._lock:
            cur = self._state.get(doc_id)
            if not isinstance(cur, dict):
                return False
            if self._is_expired(cur, now=now):
                self._state.pop(doc_id, None)
                return False
            return True
