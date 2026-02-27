"""Rbac Service module.

This module belongs to `writing_agent.web.services` in the writing-agent codebase.
"""

from __future__ import annotations

import json
from pathlib import Path


class RBACService:
    def __init__(self, policy_file: str | Path = "security/ops_rbac_policy.json") -> None:
        self.policy_file = Path(policy_file)

    def allow(self, *, role: str, action: str) -> bool:
        role_key = str(role or "viewer").strip()
        action_key = str(action or "").strip()
        if not action_key:
            return False
        policy = self._load_policy()
        roles = policy.get("roles") if isinstance(policy.get("roles"), dict) else {}
        raw_role = roles.get(role_key)
        if isinstance(raw_role, list):
            allow = [str(x) for x in raw_role]
            deny: list[str] = []
        else:
            role_row = raw_role if isinstance(raw_role, dict) else {}
            allow = role_row.get("allow") if isinstance(role_row.get("allow"), list) else []
            deny = role_row.get("deny") if isinstance(role_row.get("deny"), list) else []
        if action_key in deny:
            return False
        return action_key in allow or "*" in allow

    def _load_policy(self) -> dict:
        if not self.policy_file.exists():
            return {
                "roles": {
                    "viewer": {"allow": ["job:read", "event:read"], "deny": ["job:write", "event:write"]},
                    "editor": {"allow": ["job:read", "job:write", "event:read"], "deny": []},
                    "admin": {"allow": ["*"], "deny": []},
                }
            }
        try:
            raw = json.loads(self.policy_file.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except Exception:
            return {}
