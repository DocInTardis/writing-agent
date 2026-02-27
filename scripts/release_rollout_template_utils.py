"""Release Rollout Template Utils command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import string
from typing import Any

TRAFFIC_TEMPLATE_PLACEHOLDERS = (
    "action",
    "target_version",
    "from_version",
    "to_version",
    "correlation_id",
    "release_candidate_id",
    "from_rollout_percent",
    "to_rollout_percent",
    "canary_rollout_percent",
    "stable_rollout_percent",
    "canary_version",
    "stable_version",
    "before_canary_rollout_percent",
    "before_stable_rollout_percent",
    "before_canary_version",
    "before_stable_version",
)


def traffic_template_placeholders() -> list[str]:
    return [str(name) for name in TRAFFIC_TEMPLATE_PLACEHOLDERS]


def extract_template_placeholders(template: str) -> tuple[list[str], str]:
    text = str(template or "")
    names: set[str] = set()
    fmt = string.Formatter()
    try:
        for _, field_name, _, _ in fmt.parse(text):
            if field_name is None:
                continue
            name = str(field_name).strip()
            if not name:
                continue
            # Keep only top-level field, reject nested/index syntax for safety.
            root = name.split(".", 1)[0].split("[", 1)[0].strip()
            if root:
                names.add(root)
    except Exception as exc:
        return ([], f"{exc.__class__.__name__}:{exc}")
    return (sorted(names), "")


def validate_traffic_template(command_template: str) -> dict[str, Any]:
    text = str(command_template or "").strip()
    supported = sorted(set(traffic_template_placeholders()))
    if not text:
        return {
            "ok": True,
            "placeholders": [],
            "unknown_placeholders": [],
            "parse_error": "",
            "supported_placeholders": supported,
        }
    placeholders, parse_error = extract_template_placeholders(text)
    unknown = sorted([name for name in placeholders if name not in set(supported)])
    return {
        "ok": (not parse_error) and (len(unknown) == 0),
        "placeholders": placeholders,
        "unknown_placeholders": unknown,
        "parse_error": str(parse_error or ""),
        "supported_placeholders": supported,
    }


def build_traffic_template_context(
    *,
    plan: dict[str, Any],
    apply_result: dict[str, Any],
    store_before: dict[str, Any],
    store_after: dict[str, Any],
    correlation_id: str,
    release_candidate_id: str,
    safe_int_fn,
) -> dict[str, str]:
    before_channels = store_before.get("channels") if isinstance(store_before.get("channels"), dict) else {}
    after_channels = store_after.get("channels") if isinstance(store_after.get("channels"), dict) else {}
    before_canary = before_channels.get("canary") if isinstance(before_channels.get("canary"), dict) else {}
    before_stable = before_channels.get("stable") if isinstance(before_channels.get("stable"), dict) else {}
    after_canary = after_channels.get("canary") if isinstance(after_channels.get("canary"), dict) else {}
    after_stable = after_channels.get("stable") if isinstance(after_channels.get("stable"), dict) else {}
    action = str(plan.get("action") or "")
    target_version = str(plan.get("target_version") or "")
    from_version = str(apply_result.get("from_version") or "")
    to_version = target_version or str(apply_result.get("target_version") or "")
    return {
        "action": action,
        "target_version": target_version,
        "from_version": from_version,
        "to_version": to_version,
        "correlation_id": str(correlation_id or ""),
        "release_candidate_id": str(release_candidate_id or ""),
        "from_rollout_percent": str(safe_int_fn(apply_result.get("from_rollout_percent"), 0)),
        "to_rollout_percent": str(safe_int_fn(apply_result.get("rollout_percent"), 0)),
        "canary_rollout_percent": str(safe_int_fn(after_canary.get("rollout_percent"), 0)),
        "stable_rollout_percent": str(safe_int_fn(after_stable.get("rollout_percent"), 0)),
        "canary_version": str(after_canary.get("version") or ""),
        "stable_version": str(after_stable.get("version") or ""),
        "before_canary_rollout_percent": str(safe_int_fn(before_canary.get("rollout_percent"), 0)),
        "before_stable_rollout_percent": str(safe_int_fn(before_stable.get("rollout_percent"), 0)),
        "before_canary_version": str(before_canary.get("version") or ""),
        "before_stable_version": str(before_stable.get("version") or ""),
    }
