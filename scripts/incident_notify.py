#!/usr/bin/env python3
"""Incident Notify command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import importlib.util
import json
import os
import smtplib
import time
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


_RETRYABLE_HTTP_CODES = {408, 425, 429, 500, 502, 503, 504}

try:
    from scripts import audit_chain
except Exception:
    _AUDIT_CHAIN_PATH = Path(__file__).with_name("audit_chain.py")
    _AUDIT_SPEC = importlib.util.spec_from_file_location("audit_chain", _AUDIT_CHAIN_PATH)
    if _AUDIT_SPEC is None or _AUDIT_SPEC.loader is None:
        raise
    audit_chain = importlib.util.module_from_spec(_AUDIT_SPEC)
    _AUDIT_SPEC.loader.exec_module(audit_chain)


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


def _load_json_dict(path: Path) -> dict[str, Any]:
    raw = _load_json(path)
    return raw if isinstance(raw, dict) else {}


def _latest_report(pattern: str) -> Path | None:
    rows = sorted(Path(".").glob(pattern), key=lambda p: p.stat().st_mtime if p.exists() else 0.0)
    if not rows:
        return None
    return rows[-1]


def _latest_incident_report() -> Path | None:
    # Canonical report path should win to avoid picking drill notification outputs by mistake.
    preferred = _latest_report(".data/out/incident_report_[0-9]*.json")
    if preferred is not None:
        return preferred
    return _latest_report(".data/out/incident_report_*.json")


def _parse_csv(raw: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for part in str(raw or "").replace("\n", ",").split(","):
        item = str(part or "").strip()
        if not item:
            continue
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _signature_headers(*, body: bytes, signing_key: str, ts: int | None = None) -> dict[str, str]:
    key = str(signing_key or "").strip()
    if not key:
        return {}
    stamp = int(ts if ts is not None else time.time())
    msg = f"{stamp}.".encode("utf-8") + body
    digest = hmac.new(key.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    return {
        "X-WA-Timestamp": str(stamp),
        "X-WA-Signature": f"sha256={digest}",
    }


def _format_brief(payload: dict[str, Any]) -> str:
    node = payload.get("incident") if isinstance(payload.get("incident"), dict) else {}
    report_path = str(payload.get("report_path") or "")
    incident_id = str(node.get("incident_id") or "")
    title = str(node.get("title") or "")
    severity = str(node.get("severity") or "")
    level = str(node.get("escalation_level") or "")
    owner = str(node.get("owner") or "")
    status = str(node.get("status") or "")
    scope = str(node.get("scope") or "")
    return (
        "Writing-Agent incident notification\\n"
        f"incident_id={incident_id}\\n"
        f"title={title}\\n"
        f"severity={severity}\\n"
        f"escalation_level={level}\\n"
        f"status={status}\\n"
        f"owner={owner}\\n"
        f"scope={scope}\\n"
        f"report_path={report_path}"
    )


def _read_env(name: str, default: str = "") -> str:
    return str(os.environ.get(name, default) or "").strip()


def _http_post_json(
    *,
    url: str,
    body: dict[str, Any],
    timeout_s: float,
    signing_key: str,
) -> tuple[bool, dict[str, Any]]:
    encoded = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "writing-agent/incident-notify",
    }
    headers.update(_signature_headers(body=encoded, signing_key=signing_key))

    started = time.perf_counter()
    try:
        req = Request(str(url), data=encoded, method="POST", headers=headers)
        with urlopen(req, timeout=max(0.2, float(timeout_s))) as resp:
            status_code = int(getattr(resp, "status", 0) or resp.getcode() or 0)
        status = f"http_{status_code}" if status_code > 0 else "http_ok"
        row = {
            "ok": 200 <= status_code < 300,
            "status": status,
            "status_code": status_code,
            "retryable": status_code in _RETRYABLE_HTTP_CODES,
            "duration_s": round(float(time.perf_counter() - started), 3),
        }
        return bool(row["ok"]), row
    except HTTPError as exc:
        code = int(getattr(exc, "code", 0) or 0)
        row = {
            "ok": False,
            "status": f"http_{code}" if code > 0 else "http_error",
            "status_code": code,
            "retryable": code in _RETRYABLE_HTTP_CODES,
            "error": f"{exc.__class__.__name__}",
            "duration_s": round(float(time.perf_counter() - started), 3),
        }
        return False, row
    except URLError as exc:
        row = {
            "ok": False,
            "status": "url_error",
            "status_code": 0,
            "retryable": True,
            "error": f"{exc.__class__.__name__}",
            "duration_s": round(float(time.perf_counter() - started), 3),
        }
        return False, row
    except Exception as exc:
        row = {
            "ok": False,
            "status": "notify_exception",
            "status_code": 0,
            "retryable": True,
            "error": f"{exc.__class__.__name__}",
            "duration_s": round(float(time.perf_counter() - started), 3),
        }
        return False, row


def _notify_http_with_retry(
    *,
    channel: str,
    url: str,
    body: dict[str, Any],
    timeout_s: float,
    retries: int,
    retry_backoff_s: float,
    signing_key: str,
) -> dict[str, Any]:
    attempts: list[dict[str, Any]] = []
    max_attempts = max(1, int(retries) + 1)
    backoff = max(0.0, float(retry_backoff_s))
    ok = False
    status = "not_sent"
    for idx in range(max_attempts):
        ok, row = _http_post_json(
            url=url,
            body=body,
            timeout_s=timeout_s,
            signing_key=signing_key,
        )
        attempt = dict(row)
        attempt["attempt"] = idx + 1
        attempts.append(attempt)
        status = str(attempt.get("status") or "")
        if ok:
            break
        retryable = bool(attempt.get("retryable"))
        if idx + 1 < max_attempts and retryable and backoff > 0:
            time.sleep(backoff * float(idx + 1))
    return {
        "channel": str(channel),
        "target": str(url),
        "ok": bool(ok),
        "status": str(status),
        "attempts": attempts,
    }


def _notify_email(
    *,
    to_list: list[str],
    from_addr: str,
    smtp_host: str,
    smtp_port: int,
    starttls: bool,
    smtp_user: str,
    smtp_password: str,
    timeout_s: float,
    subject: str,
    body_text: str,
) -> dict[str, Any]:
    if not to_list or not from_addr or not smtp_host:
        return {
            "channel": "email",
            "target": ",".join(to_list),
            "ok": False,
            "status": "email_config_missing",
            "attempts": [
                {
                    "attempt": 1,
                    "ok": False,
                    "status": "email_config_missing",
                    "status_code": 0,
                    "retryable": False,
                    "duration_s": 0.0,
                }
            ],
        }

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = from_addr
    msg["To"] = ", ".join(to_list)
    msg.set_content(body_text)

    started = time.perf_counter()
    try:
        with smtplib.SMTP(host=smtp_host, port=int(smtp_port), timeout=max(0.2, float(timeout_s))) as smtp:
            smtp.ehlo()
            if starttls:
                smtp.starttls()
                smtp.ehlo()
            if smtp_user:
                smtp.login(smtp_user, smtp_password)
            smtp.send_message(msg)
        row = {
            "attempt": 1,
            "ok": True,
            "status": "smtp_250",
            "status_code": 250,
            "retryable": False,
            "duration_s": round(float(time.perf_counter() - started), 3),
        }
        return {
            "channel": "email",
            "target": ",".join(to_list),
            "ok": True,
            "status": "smtp_250",
            "attempts": [row],
        }
    except smtplib.SMTPException as exc:
        row = {
            "attempt": 1,
            "ok": False,
            "status": "smtp_error",
            "status_code": 0,
            "retryable": True,
            "error": f"{exc.__class__.__name__}",
            "duration_s": round(float(time.perf_counter() - started), 3),
        }
        return {
            "channel": "email",
            "target": ",".join(to_list),
            "ok": False,
            "status": "smtp_error",
            "attempts": [row],
        }
    except Exception as exc:
        row = {
            "attempt": 1,
            "ok": False,
            "status": "email_exception",
            "status_code": 0,
            "retryable": True,
            "error": f"{exc.__class__.__name__}",
            "duration_s": round(float(time.perf_counter() - started), 3),
        }
        return {
            "channel": "email",
            "target": ",".join(to_list),
            "ok": False,
            "status": "email_exception",
            "attempts": [row],
        }


def _severity_rank(severity: str) -> int:
    value = str(severity or "").strip().lower()
    table = {
        "critical": 4,
        "high": 3,
        "medium": 2,
        "low": 1,
        "warn": 1,
        "info": 0,
    }
    return int(table.get(value, 0))


def _load_routing_policy(path: Path) -> dict[str, Any]:
    raw = _load_json(path)
    if isinstance(raw, dict):
        return raw
    return {}


def _load_oncall_roster(path: Path) -> dict[str, Any]:
    raw = _load_json(path)
    return raw if isinstance(raw, dict) else {}


def _oncall_target_from_roster(roster: dict[str, Any]) -> dict[str, Any]:
    primary = roster.get("primary") if isinstance(roster.get("primary"), dict) else {}
    if isinstance(primary, dict) and primary:
        return primary
    rotations = roster.get("rotations") if isinstance(roster.get("rotations"), list) else []
    active = [row for row in rotations if isinstance(row, dict) and bool(row.get("active"))]
    picked = active[0] if active else (rotations[0] if rotations and isinstance(rotations[0], dict) else {})
    return picked if isinstance(picked, dict) else {}


def _oncall_email_list(target: dict[str, Any]) -> list[str]:
    emails = target.get("email") if isinstance(target.get("email"), list) else []
    return _parse_csv(",".join(str(item) for item in emails))


def _apply_oncall_target(
    *,
    webhook_url: str,
    slack_webhook_url: str,
    feishu_webhook_url: str,
    email_to: list[str],
    oncall_target: dict[str, Any],
    prefer_roster: bool,
) -> tuple[dict[str, Any], bool]:
    target_email = _oncall_email_list(oncall_target)
    target_webhook = str(oncall_target.get("webhook_url") or "").strip()
    target_slack = str(oncall_target.get("slack_webhook_url") or "").strip()
    target_feishu = str(oncall_target.get("feishu_webhook_url") or "").strip()

    applied = False
    out_webhook = str(webhook_url or "").strip()
    out_slack = str(slack_webhook_url or "").strip()
    out_feishu = str(feishu_webhook_url or "").strip()
    out_email = list(email_to or [])

    if target_webhook and (prefer_roster or not out_webhook):
        out_webhook = target_webhook
        applied = True
    if target_slack and (prefer_roster or not out_slack):
        out_slack = target_slack
        applied = True
    if target_feishu and (prefer_roster or not out_feishu):
        out_feishu = target_feishu
        applied = True
    if target_email:
        merged = _parse_csv(",".join([*target_email, *out_email]))
        if merged != out_email:
            out_email = merged
            applied = True

    return {
        "webhook_url": out_webhook,
        "slack_webhook_url": out_slack,
        "feishu_webhook_url": out_feishu,
        "email_to": out_email,
    }, applied


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _rule_time_match(rule: dict[str, Any], incident: dict[str, Any]) -> bool:
    ts = _safe_float(incident.get("created_at"), 0.0)
    dt = datetime.fromtimestamp(ts, tz=timezone.utc) if ts > 0 else datetime.now(tz=timezone.utc)

    days = [_safe_int(x, -1) for x in (rule.get("days_of_week") if isinstance(rule.get("days_of_week"), list) else [])]
    days = [x for x in days if 0 <= x <= 6]
    if days and dt.weekday() not in days:
        return False

    hours = rule.get("hours_utc") if isinstance(rule.get("hours_utc"), dict) else {}
    if hours:
        start = _safe_int(hours.get("start"), -1)
        end = _safe_int(hours.get("end"), -1)
        if 0 <= start <= 23 and 0 <= end <= 23:
            hour = dt.hour
            if start <= end:
                return start <= hour <= end
            return hour >= start or hour <= end
    return True


def _routing_targets(
    *,
    routing_policy: dict[str, Any],
    incident: dict[str, Any],
    configured: set[str],
) -> set[str]:
    rules = routing_policy.get("rules") if isinstance(routing_policy.get("rules"), list) else []
    if not rules:
        return set(configured)

    incident_severity = str(incident.get("severity") or "").strip().lower()
    incident_owner = str(incident.get("owner") or "").strip().lower()

    selected: set[str] = set()
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        enabled = bool(rule.get("enabled", True))
        if not enabled:
            continue
        min_severity = str(rule.get("min_severity") or "").strip().lower()
        if min_severity and _severity_rank(incident_severity) < _severity_rank(min_severity):
            continue
        owners = [
            str(x).strip().lower()
            for x in (rule.get("owners") if isinstance(rule.get("owners"), list) else [])
            if str(x).strip()
        ]
        if owners and incident_owner and incident_owner not in owners:
            continue
        if not _rule_time_match(rule, incident):
            continue
        channels = [
            str(x).strip().lower()
            for x in (rule.get("channels") if isinstance(rule.get("channels"), list) else [])
            if str(x).strip()
        ]
        for channel in channels:
            if channel in configured:
                selected.add(channel)

    if selected:
        return selected
    fallback = [
        str(x).strip().lower()
        for x in (routing_policy.get("default_channels") if isinstance(routing_policy.get("default_channels"), list) else [])
        if str(x).strip()
    ]
    picked = {item for item in fallback if item in configured}
    return picked if picked else set(configured)


def _dead_letter_write(
    *,
    dead_letter_dir: Path,
    payload: dict[str, Any],
    reason: str,
    channels: list[dict[str, Any]],
) -> Path:
    dead_letter_dir.mkdir(parents=True, exist_ok=True)
    ts = int(time.time() * 1000)
    out = dead_letter_dir / f"incident_notify_dead_letter_{ts}.json"
    data = {
        "schema_version": 1,
        "created_at": round(time.time(), 3),
        "reason": str(reason),
        "payload": payload,
        "channels": channels,
    }
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def _build_message_payload(incident_report: dict[str, Any], report_path: Path, source: str) -> dict[str, Any]:
    incident = incident_report.get("incident") if isinstance(incident_report.get("incident"), dict) else {}
    base = {
        "schema_version": 1,
        "source": str(source),
        "report_path": report_path.as_posix(),
        "incident": incident,
        "generated_at": round(time.time(), 3),
    }
    brief = _format_brief(base)
    base["brief"] = brief
    return base


def _notify_once(
    *,
    payload: dict[str, Any],
    timeout_s: float,
    retries: int,
    retry_backoff_s: float,
    signing_key: str,
    webhook_url: str,
    slack_webhook_url: str,
    feishu_webhook_url: str,
    email_to: list[str],
    email_from: str,
    smtp_host: str,
    smtp_port: int,
    smtp_starttls: bool,
    smtp_user: str,
    smtp_password: str,
    routing_policy: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    incident = payload.get("incident") if isinstance(payload.get("incident"), dict) else {}

    configured: set[str] = set()
    if webhook_url:
        configured.add("webhook")
    if slack_webhook_url:
        configured.add("slack")
    if feishu_webhook_url:
        configured.add("feishu")
    if email_to and email_from and smtp_host:
        configured.add("email")

    chosen = _routing_targets(routing_policy=routing_policy, incident=incident, configured=configured)

    channels: list[dict[str, Any]] = []
    if "webhook" in chosen:
        channels.append(
            _notify_http_with_retry(
                channel="webhook",
                url=webhook_url,
                body=payload,
                timeout_s=timeout_s,
                retries=retries,
                retry_backoff_s=retry_backoff_s,
                signing_key=signing_key,
            )
        )
    if "slack" in chosen:
        channels.append(
            _notify_http_with_retry(
                channel="slack",
                url=slack_webhook_url,
                body={"text": str(payload.get("brief") or "")},
                timeout_s=timeout_s,
                retries=retries,
                retry_backoff_s=retry_backoff_s,
                signing_key="",
            )
        )
    if "feishu" in chosen:
        channels.append(
            _notify_http_with_retry(
                channel="feishu",
                url=feishu_webhook_url,
                body={"msg_type": "text", "content": {"text": str(payload.get("brief") or "")}},
                timeout_s=timeout_s,
                retries=retries,
                retry_backoff_s=retry_backoff_s,
                signing_key="",
            )
        )
    if "email" in chosen:
        channels.append(
            _notify_email(
                to_list=email_to,
                from_addr=email_from,
                smtp_host=smtp_host,
                smtp_port=smtp_port,
                starttls=smtp_starttls,
                smtp_user=smtp_user,
                smtp_password=smtp_password,
                timeout_s=timeout_s,
                subject=f"[writing-agent] incident {((incident.get('incident_id') if isinstance(incident, dict) else '') or '').strip()}",
                body_text=str(payload.get("brief") or ""),
            )
        )

    return channels, sorted(chosen)


def _strict_fail(strict: bool, channel_rows: list[dict[str, Any]], configured_any: bool) -> bool:
    if not strict:
        return False
    if not configured_any:
        return True
    return any(not bool(row.get("ok")) for row in channel_rows)


def _normalize_bool(raw: str | bool | None, default: bool = False) -> bool:
    if isinstance(raw, bool):
        return raw
    text = str(raw or "").strip().lower()
    if not text:
        return bool(default)
    return text in {"1", "true", "yes", "on"}


def _maybe_resolve_dead_letter(path_value: str) -> Path | None:
    path = Path(str(path_value or "").strip())
    if not str(path).strip():
        return None
    if path.exists() and path.is_file():
        return path
    if path.exists() and path.is_dir():
        rows = sorted(path.glob("incident_notify_dead_letter_*.json"), key=lambda p: p.stat().st_mtime)
        if rows:
            return rows[-1]
        return None
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Send incident report notifications to configured external channels.")
    parser.add_argument("--incident-report", default="")
    parser.add_argument("--only-when-escalated", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--source", default="release-preflight")

    parser.add_argument("--webhook-url", default="")
    parser.add_argument("--slack-webhook-url", default="")
    parser.add_argument("--feishu-webhook-url", default="")
    parser.add_argument("--signing-key", default="")

    parser.add_argument("--email-to", default="")
    parser.add_argument("--email-from", default="")
    parser.add_argument("--smtp-host", default="")
    parser.add_argument("--smtp-port", type=int, default=25)
    parser.add_argument("--smtp-starttls", default="1")
    parser.add_argument("--smtp-user", default="")
    parser.add_argument("--smtp-password", default="")

    parser.add_argument("--timeout-s", type=float, default=6.0)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--retry-backoff-s", type=float, default=1.0)

    parser.add_argument("--routing-policy", default="security/incident_routing.json")
    parser.add_argument("--oncall-roster", default="")
    parser.add_argument("--prefer-oncall-roster", default="")
    parser.add_argument("--dead-letter-dir", default=".data/out/dead_letter")
    parser.add_argument("--replay-dead-letter", default="")
    parser.add_argument("--audit-log", default="")
    parser.add_argument("--audit-state-file", default="")
    parser.add_argument("--audit-actor", default="")
    parser.add_argument("--skip-audit-log", action="store_true")
    parser.add_argument("--audit-strict", action="store_true")

    parser.add_argument("--out", default="")
    args = parser.parse_args()

    started = time.time()
    timeout_s = max(0.2, float(args.timeout_s))

    webhook_url = str(args.webhook_url or _read_env("WA_INCIDENT_WEBHOOK_URL")).strip()
    slack_webhook_url = str(args.slack_webhook_url or _read_env("WA_INCIDENT_SLACK_WEBHOOK_URL")).strip()
    feishu_webhook_url = str(args.feishu_webhook_url or _read_env("WA_INCIDENT_FEISHU_WEBHOOK_URL")).strip()
    signing_key = str(args.signing_key or _read_env("WA_INCIDENT_SIGNING_KEY")).strip()

    email_to = _parse_csv(str(args.email_to or _read_env("WA_INCIDENT_EMAIL_TO")))
    email_from = str(args.email_from or _read_env("WA_INCIDENT_EMAIL_FROM")).strip()
    smtp_host = str(args.smtp_host or _read_env("WA_INCIDENT_SMTP_HOST")).strip()
    smtp_port = int(str(args.smtp_port or _read_env("WA_INCIDENT_SMTP_PORT") or 25))
    smtp_starttls = _normalize_bool(str(args.smtp_starttls or _read_env("WA_INCIDENT_SMTP_STARTTLS", "1")), default=True)
    smtp_user = str(args.smtp_user or _read_env("WA_INCIDENT_SMTP_USER")).strip()
    smtp_password = str(args.smtp_password or _read_env("WA_INCIDENT_SMTP_PASSWORD")).strip()

    routing_policy_path = Path(str(args.routing_policy))
    routing_policy = _load_routing_policy(routing_policy_path)
    oncall_roster_path = Path(str(args.oncall_roster or _read_env("WA_INCIDENT_ONCALL_ROSTER_FILE", "security/oncall_roster.json")))
    prefer_oncall_roster = _normalize_bool(
        str(args.prefer_oncall_roster or _read_env("WA_INCIDENT_USE_ONCALL_ROSTER", "1")),
        default=True,
    )
    oncall_roster_raw = _load_oncall_roster(oncall_roster_path)
    oncall_target = _oncall_target_from_roster(oncall_roster_raw)
    oncall_applied = False
    if prefer_oncall_roster and oncall_target:
        updated_targets, oncall_applied = _apply_oncall_target(
            webhook_url=webhook_url,
            slack_webhook_url=slack_webhook_url,
            feishu_webhook_url=feishu_webhook_url,
            email_to=email_to,
            oncall_target=oncall_target,
            prefer_roster=prefer_oncall_roster,
        )
        webhook_url = str(updated_targets.get("webhook_url") or "").strip()
        slack_webhook_url = str(updated_targets.get("slack_webhook_url") or "").strip()
        feishu_webhook_url = str(updated_targets.get("feishu_webhook_url") or "").strip()
        email_to = _parse_csv(",".join(updated_targets.get("email_to") if isinstance(updated_targets.get("email_to"), list) else []))

    dead_letter_dir = Path(str(args.dead_letter_dir))
    replay_target = _maybe_resolve_dead_letter(str(args.replay_dead_letter))

    incident_report_path: Path | None = None
    incident_report_raw: dict[str, Any] = {}
    mode = "normal"

    if replay_target is not None:
        mode = "replay"
        dead_letter_raw = _load_json_dict(replay_target)
        payload = dead_letter_raw.get("payload") if isinstance(dead_letter_raw.get("payload"), dict) else {}
        if payload:
            incident_report_raw = {"incident": payload.get("incident") if isinstance(payload.get("incident"), dict) else {}}
            incident_report_path = Path(str(payload.get("report_path") or "")) if str(payload.get("report_path") or "").strip() else None
            notify_payload = payload
        else:
            incident_report_path = None
            notify_payload = {
                "schema_version": 1,
                "source": str(args.source),
                "report_path": replay_target.as_posix(),
                "incident": {},
                "generated_at": round(time.time(), 3),
                "brief": "dead-letter payload missing",
            }
    else:
        incident_report_path = Path(str(args.incident_report)) if str(args.incident_report).strip() else _latest_incident_report()
        incident_report_raw = _load_json_dict(incident_report_path) if isinstance(incident_report_path, Path) else {}
        notify_payload = _build_message_payload(
            incident_report=incident_report_raw,
            report_path=incident_report_path if isinstance(incident_report_path, Path) else Path(""),
            source=str(args.source),
        )

    incident = notify_payload.get("incident") if isinstance(notify_payload.get("incident"), dict) else {}
    level = str(incident.get("escalation_level") or "none").strip().lower()
    should_skip = bool(args.only_when_escalated and level in {"", "none"} and mode != "replay")

    configured_any = any(
        [
            bool(webhook_url),
            bool(slack_webhook_url),
            bool(feishu_webhook_url),
            bool(email_to and email_from and smtp_host),
        ]
    )

    channels: list[dict[str, Any]] = []
    routed_channels: list[str] = []
    dead_letter_path = ""

    if not should_skip:
        channels, routed_channels = _notify_once(
            payload=notify_payload,
            timeout_s=timeout_s,
            retries=max(0, int(args.retries)),
            retry_backoff_s=max(0.0, float(args.retry_backoff_s)),
            signing_key=signing_key,
            webhook_url=webhook_url,
            slack_webhook_url=slack_webhook_url,
            feishu_webhook_url=feishu_webhook_url,
            email_to=email_to,
            email_from=email_from,
            smtp_host=smtp_host,
            smtp_port=smtp_port,
            smtp_starttls=smtp_starttls,
            smtp_user=smtp_user,
            smtp_password=smtp_password,
            routing_policy=routing_policy,
        )

    ok = bool(not should_skip)
    reason = ""

    if should_skip:
        ok = True
        reason = "no_escalation"
    elif not channels:
        ok = False
        reason = "no_channel_selected"
    else:
        ok = all(bool(row.get("ok")) for row in channels)
        if not ok:
            reason = "channel_failed"

    if (not ok) and not should_skip:
        dead_path = _dead_letter_write(
            dead_letter_dir=dead_letter_dir,
            payload=notify_payload,
            reason=reason or "notify_failed",
            channels=channels,
        )
        dead_letter_path = dead_path.as_posix()

    ended = time.time()
    report = {
        "ok": bool(ok) and not _strict_fail(bool(args.strict), channels, configured_any),
        "skipped": bool(should_skip),
        "reason": reason,
        "mode": mode,
        "started_at": round(started, 3),
        "ended_at": round(ended, 3),
        "duration_s": round(ended - started, 3),
        "incident_report": incident_report_path.as_posix() if isinstance(incident_report_path, Path) else "",
        "routing_policy": routing_policy_path.as_posix(),
        "routed_channels": routed_channels,
        "channels": channels,
        "dead_letter_path": dead_letter_path,
        "oncall_roster": {
            "path": oncall_roster_path.as_posix(),
            "loaded": bool(oncall_roster_raw),
            "prefer_roster": bool(prefer_oncall_roster),
            "used": bool(oncall_applied),
            "target": {
                "has_webhook": bool(str(oncall_target.get("webhook_url") or "").strip()),
                "has_slack": bool(str(oncall_target.get("slack_webhook_url") or "").strip()),
                "has_feishu": bool(str(oncall_target.get("feishu_webhook_url") or "").strip()),
                "email_count": len(_oncall_email_list(oncall_target)),
            },
        },
        "strict": bool(args.strict),
        "only_when_escalated": bool(args.only_when_escalated),
    }

    audit_result: dict[str, Any] = {"ok": True, "skipped": True}
    if not bool(args.skip_audit_log):
        audit_actor = str(args.audit_actor or "").strip() or "incident-bot"
        audit_result = audit_chain.record_operation(
            action="incident_notify",
            actor=audit_actor,
            source="incident_notify",
            status="ok" if bool(report.get("ok")) else "failed",
            context={
                "mode": mode,
                "reason": str(reason or ""),
                "source": str(args.source or ""),
                "skipped": bool(should_skip),
                "strict": bool(args.strict),
                "only_when_escalated": bool(args.only_when_escalated),
                "incident_report": incident_report_path.as_posix() if isinstance(incident_report_path, Path) else "",
                "routed_channels": routed_channels,
                "channel_count": len(channels),
                "dead_letter_path": dead_letter_path,
            },
            log_path=str(args.audit_log or ""),
            state_path=str(args.audit_state_file or ""),
            strict=False,
        )
    report["audit"] = audit_result
    if bool(args.audit_strict) and (not bool(audit_result.get("ok"))):
        report["ok"] = False

    out_default = Path(".data/out") / f"incident_notify_{int(ended)}.json"
    out_path = Path(str(args.out or out_default))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if bool(report.get("ok")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
