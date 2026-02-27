#!/usr/bin/env python3
"""Incident Config Guard command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any] | list[Any] | None:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if isinstance(raw, (dict, list)):
        return raw
    return None


def _parse_csv(raw: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for part in str(raw or "").replace("\n", ",").split(","):
        item = str(part or "").strip()
        if not item:
            continue
        lower = item.lower()
        if lower in seen:
            continue
        seen.add(lower)
        out.append(item)
    return out


def _ok(*, check_id: str, ok: bool, value: Any, expect: str, mode: str = "enforce") -> dict[str, Any]:
    return {
        "id": str(check_id),
        "ok": bool(ok),
        "value": value,
        "expect": str(expect),
        "mode": str(mode or "enforce"),
    }


def _env(name: str, default: str = "") -> str:
    return str(os.environ.get(name, default) or "").strip()


def _normalize_channels(
    *,
    webhook_url: str,
    slack_webhook_url: str,
    feishu_webhook_url: str,
    email_to: list[str],
    email_from: str,
    smtp_host: str,
) -> dict[str, bool]:
    return {
        "webhook": bool(webhook_url),
        "slack": bool(slack_webhook_url),
        "feishu": bool(feishu_webhook_url),
        "email": bool(email_to and email_from and smtp_host),
    }


def _extract_policy_channels(policy_raw: dict[str, Any]) -> set[str]:
    out: set[str] = set()
    default_channels = policy_raw.get("default_channels") if isinstance(policy_raw.get("default_channels"), list) else []
    for item in default_channels:
        value = str(item or "").strip().lower()
        if value:
            out.add(value)
    rules = policy_raw.get("rules") if isinstance(policy_raw.get("rules"), list) else []
    for row in rules:
        if not isinstance(row, dict):
            continue
        channels = row.get("channels") if isinstance(row.get("channels"), list) else []
        for item in channels:
            value = str(item or "").strip().lower()
            if value:
                out.add(value)
    return out


def _extract_oncall_target(roster_raw: dict[str, Any]) -> dict[str, Any]:
    primary = roster_raw.get("primary") if isinstance(roster_raw.get("primary"), dict) else {}
    if isinstance(primary, dict) and primary:
        return primary
    rotations = roster_raw.get("rotations") if isinstance(roster_raw.get("rotations"), list) else []
    active = [row for row in rotations if isinstance(row, dict) and bool(row.get("active"))]
    picked = active[0] if active else (rotations[0] if rotations and isinstance(rotations[0], dict) else {})
    return picked if isinstance(picked, dict) else {}


def _oncall_target_presence(target: dict[str, Any]) -> dict[str, Any]:
    emails = target.get("email") if isinstance(target.get("email"), list) else []
    email_rows = [str(item).strip() for item in emails if str(item).strip()]
    return {
        "webhook": bool(str(target.get("webhook_url") or "").strip()),
        "slack": bool(str(target.get("slack_webhook_url") or "").strip()),
        "feishu": bool(str(target.get("feishu_webhook_url") or "").strip()),
        "email_count": len(email_rows),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate incident notification channel configuration and routing policy.")
    parser.add_argument("--webhook-url", default="")
    parser.add_argument("--slack-webhook-url", default="")
    parser.add_argument("--feishu-webhook-url", default="")
    parser.add_argument("--email-to", default="")
    parser.add_argument("--email-from", default="")
    parser.add_argument("--smtp-host", default="")
    parser.add_argument("--smtp-port", default="")
    parser.add_argument("--routing-policy", default="security/incident_routing.json")
    parser.add_argument("--oncall-roster", default="")
    parser.add_argument("--require-oncall-roster", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    started = time.time()
    checks: list[dict[str, Any]] = []

    webhook_url = str(args.webhook_url or _env("WA_INCIDENT_WEBHOOK_URL"))
    slack_webhook_url = str(args.slack_webhook_url or _env("WA_INCIDENT_SLACK_WEBHOOK_URL"))
    feishu_webhook_url = str(args.feishu_webhook_url or _env("WA_INCIDENT_FEISHU_WEBHOOK_URL"))
    email_to = _parse_csv(str(args.email_to or _env("WA_INCIDENT_EMAIL_TO")))
    email_from = str(args.email_from or _env("WA_INCIDENT_EMAIL_FROM"))
    smtp_host = str(args.smtp_host or _env("WA_INCIDENT_SMTP_HOST"))
    smtp_port = str(args.smtp_port or _env("WA_INCIDENT_SMTP_PORT"))

    configured = _normalize_channels(
        webhook_url=webhook_url,
        slack_webhook_url=slack_webhook_url,
        feishu_webhook_url=feishu_webhook_url,
        email_to=email_to,
        email_from=email_from,
        smtp_host=smtp_host,
    )
    configured_count = sum(1 for _, enabled in configured.items() if enabled)
    checks.append(
        _ok(
            check_id="at_least_one_incident_channel_configured",
            ok=configured_count > 0,
            value=configured,
            expect=">=1 of webhook/slack/feishu/email configured",
            mode="enforce" if bool(args.strict) else "warn",
        )
    )

    email_raw_present = bool(email_to) or bool(email_from) or bool(smtp_host) or bool(smtp_port)
    checks.append(
        _ok(
            check_id="email_config_complete_if_present",
            ok=(not email_raw_present) or bool(email_to and email_from and smtp_host),
            value={
                "email_to_count": len(email_to),
                "email_from": bool(email_from),
                "smtp_host": bool(smtp_host),
                "smtp_port": bool(smtp_port),
            },
            expect="if any email field exists then email_to/email_from/smtp_host must all be set",
            mode="enforce",
        )
    )

    policy_path = Path(str(args.routing_policy))
    policy_raw = _load_json(policy_path)
    checks.append(
        _ok(
            check_id="incident_routing_policy_loaded",
            ok=isinstance(policy_raw, dict),
            value=policy_path.as_posix(),
            expect="routing policy json exists and parseable",
            mode="enforce",
        )
    )

    supported_channels = {"webhook", "slack", "feishu", "email"}
    policy_channels = _extract_policy_channels(policy_raw if isinstance(policy_raw, dict) else {})
    unknown_channels = sorted([item for item in policy_channels if item not in supported_channels])
    checks.append(
        _ok(
            check_id="incident_routing_channels_supported",
            ok=len(unknown_channels) == 0,
            value={"policy_channels": sorted(policy_channels), "unknown_channels": unknown_channels},
            expect="routing policy channels subset of webhook/slack/feishu/email",
            mode="enforce",
        )
    )

    oncall_roster_path = Path(str(args.oncall_roster or _env("WA_INCIDENT_ONCALL_ROSTER_FILE", "security/oncall_roster.json")))
    require_oncall_env = _env("WA_INCIDENT_REQUIRE_ONCALL_ROSTER", "").strip().lower()
    require_oncall = bool(args.require_oncall_roster) or require_oncall_env in {"1", "true", "yes", "on"}
    oncall_raw = _load_json(oncall_roster_path)
    oncall_target = _extract_oncall_target(oncall_raw if isinstance(oncall_raw, dict) else {})
    oncall_presence = _oncall_target_presence(oncall_target)
    oncall_mode = "enforce" if (bool(args.strict) or require_oncall) else "warn"
    checks.append(
        _ok(
            check_id="oncall_roster_loaded",
            ok=isinstance(oncall_raw, dict) if require_oncall else True,
            value={"path": oncall_roster_path.as_posix(), "exists": oncall_roster_path.exists()},
            expect="on-call roster exists and is valid json when required",
            mode=oncall_mode,
        )
    )
    checks.append(
        _ok(
            check_id="oncall_target_present",
            ok=(sum([int(bool(oncall_presence["webhook"])), int(bool(oncall_presence["slack"])), int(bool(oncall_presence["feishu"])), int(oncall_presence["email_count"] > 0)]) > 0)
            if require_oncall
            else True,
            value=oncall_presence,
            expect="on-call target includes at least one reachable channel when required",
            mode=oncall_mode,
        )
    )

    ended = time.time()
    enforce_rows = [row for row in checks if str(row.get("mode") or "enforce") == "enforce"]
    report = {
        "ok": all(bool(row.get("ok")) for row in enforce_rows),
        "started_at": round(started, 3),
        "ended_at": round(ended, 3),
        "duration_s": round(ended - started, 3),
        "strict": bool(args.strict),
        "configured_channels": configured,
        "checks": checks,
    }

    out_default = Path(".data/out") / f"incident_config_guard_{int(ended)}.json"
    out_path = Path(str(args.out or out_default))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if bool(report.get("ok")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
