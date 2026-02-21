#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def _extract_failed_check_ids(text: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in str(text or "").splitlines():
        line = str(raw or "").strip()
        if not line.startswith("- "):
            continue
        body = line[2:].strip()
        check_id = str(body.split(":", 1)[0] or "").strip()
        if not check_id or check_id in seen:
            continue
        seen.add(check_id)
        out.append(check_id)
        if len(out) >= 48:
            break
    return out


def _triage_hints(check_ids: list[str]) -> list[str]:
    hints: list[str] = []
    if any("regression" in cid for cid in check_ids):
        hints.append("Compare with security/dependency_baseline.json and justify baseline updates.")
    if any(cid.startswith("npm_prod_") for cid in check_ids):
        hints.append("Fix production npm vulnerabilities first; dev-only fixes are not sufficient.")
    if any(cid.startswith("npm_dev_") for cid in check_ids):
        hints.append("Upgrade or replace vulnerable dev dependencies and rerun npm audit.")
    if any(cid.startswith("pip_") for cid in check_ids):
        hints.append("Run pip-audit locally and patch vulnerable Python dependencies.")
    if any("tool_present" in cid for cid in check_ids):
        hints.append("Ensure pip-audit is installed and required in CI/preflight environments.")
    if not hints:
        hints.append("Review dependency audit report artifact and remediate failed enforce checks.")
    return hints[:8]


def _alert_severity(check_ids: list[str]) -> str:
    if any("critical" in cid for cid in check_ids):
        return "critical"
    if any("high" in cid for cid in check_ids):
        return "high"
    return "warn"


def _parse_ids_arg(raw: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for part in str(raw or "").replace("\n", ",").split(","):
        item = str(part or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
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


def _post_once(
    *,
    url: str,
    payload: dict[str, Any],
    signing_key: str,
    timeout_s: float,
) -> tuple[bool, dict[str, Any]]:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "writing-agent/security-alert-notify",
    }
    headers.update(_signature_headers(body=body, signing_key=signing_key))

    started = time.perf_counter()
    try:
        req = Request(str(url), data=body, headers=headers, method="POST")
        with urlopen(req, timeout=max(0.2, float(timeout_s))) as resp:
            code = int(getattr(resp, "status", 0) or resp.getcode() or 0)
        row = {
            "ok": 200 <= code < 300,
            "status_code": code,
            "status": f"http_{code}",
            "duration_s": round(float(time.perf_counter() - started), 3),
            "signature_enabled": bool(str(signing_key or "").strip()),
        }
        return bool(row["ok"]), row
    except HTTPError as exc:
        code = int(getattr(exc, "code", 0) or 0)
        row = {
            "ok": False,
            "status_code": code,
            "status": f"http_{code}" if code > 0 else "http_error",
            "error": f"{exc.__class__.__name__}",
            "duration_s": round(float(time.perf_counter() - started), 3),
            "signature_enabled": bool(str(signing_key or "").strip()),
        }
        return False, row
    except URLError as exc:
        row = {
            "ok": False,
            "status_code": 0,
            "status": "url_error",
            "error": f"{exc.__class__.__name__}",
            "duration_s": round(float(time.perf_counter() - started), 3),
            "signature_enabled": bool(str(signing_key or "").strip()),
        }
        return False, row
    except Exception as exc:
        row = {
            "ok": False,
            "status_code": 0,
            "status": "notify_exception",
            "error": f"{exc.__class__.__name__}",
            "duration_s": round(float(time.perf_counter() - started), 3),
            "signature_enabled": bool(str(signing_key or "").strip()),
        }
        return False, row


def main() -> int:
    parser = argparse.ArgumentParser(description="Send dependency-security alert webhook with optional signature.")
    parser.add_argument("--url", required=True)
    parser.add_argument("--source", default="dependency-security-workflow")
    parser.add_argument("--status", default="failed")
    parser.add_argument("--repo", default="")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--run-number", default="")
    parser.add_argument("--run-url", default="")
    parser.add_argument("--artifact-url", default="")
    parser.add_argument("--summary", default="")
    parser.add_argument("--details", default="")
    parser.add_argument("--failed-check-ids", default="")
    parser.add_argument("--simulate-failure", default="")
    parser.add_argument("--signing-key", default="")
    parser.add_argument("--timeout-s", type=float, default=8.0)
    parser.add_argument("--retries", type=int, default=2)
    parser.add_argument("--retry-backoff-s", type=float, default=1.0)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    failed_ids = _parse_ids_arg(str(args.failed_check_ids))
    if not failed_ids:
        failed_ids = _extract_failed_check_ids(str(args.details))

    simulate_raw = str(args.simulate_failure or "").strip().lower()
    simulate = simulate_raw in {"1", "true", "yes", "on"}
    payload = {
        "schema_version": 1,
        "source": str(args.source),
        "kind": "dependency_security",
        "status": str(args.status),
        "severity": _alert_severity(failed_ids),
        "timestamp": round(time.time(), 3),
        "repo": str(args.repo),
        "run_id": str(args.run_id),
        "run_number": str(args.run_number),
        "run_url": str(args.run_url),
        "artifact_url": str(args.artifact_url),
        "summary": str(args.summary),
        "details": str(args.details),
        "failed_check_ids": failed_ids,
        "triage_hints": _triage_hints(failed_ids),
        "simulate_failure": bool(simulate),
    }

    started = time.time()
    attempts: list[dict[str, Any]] = []
    max_attempts = max(1, int(args.retries) + 1)
    backoff = max(0.0, float(args.retry_backoff_s))
    ok = False
    final_status = "not_sent"
    for idx in range(max_attempts):
        ok, row = _post_once(
            url=str(args.url),
            payload=payload,
            signing_key=str(args.signing_key or ""),
            timeout_s=max(0.2, float(args.timeout_s)),
        )
        row["attempt"] = idx + 1
        attempts.append(row)
        final_status = str(row.get("status") or "")
        if ok:
            break
        status_code = int(row.get("status_code") or 0)
        retryable = (status_code == 0) or (status_code >= 500)
        if idx + 1 < max_attempts and retryable and backoff > 0:
            time.sleep(backoff * float(idx + 1))

    ended = time.time()
    report = {
        "ok": ok,
        "status": final_status,
        "started_at": round(started, 3),
        "ended_at": round(ended, 3),
        "duration_s": round(ended - started, 3),
        "attempts": attempts,
        "payload": payload,
    }
    out_default = Path(".data/out") / f"security_alert_notify_{int(ended)}.json"
    out_path = Path(str(args.out or out_default))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
