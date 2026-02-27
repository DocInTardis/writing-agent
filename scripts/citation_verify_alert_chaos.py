#!/usr/bin/env python3
"""Citation Verify Alert Chaos command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def _json_request(
    method: str,
    url: str,
    *,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout_s: float = 6.0,
) -> tuple[int, dict[str, Any]]:
    req_headers = dict(headers or {})
    payload = None
    if body is not None:
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req_headers["Content-Type"] = "application/json"
    req = Request(url, data=payload, headers=req_headers, method=method.upper())
    with urlopen(req, timeout=max(0.2, float(timeout_s))) as resp:
        status = int(getattr(resp, "status", 0) or resp.getcode() or 0)
        raw = resp.read()
    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    return status, data


def _wait_ready(base_url: str, *, timeout_s: float) -> None:
    deadline = time.time() + max(2.0, float(timeout_s))
    url = f"{base_url.rstrip('/')}/api/metrics/citation_verify"
    last_err = "not_ready"
    while time.time() < deadline:
        try:
            status, _ = _json_request("GET", url, timeout_s=1.5)
            if 200 <= status < 300:
                return
            last_err = f"http_{status}"
        except Exception as exc:
            last_err = exc.__class__.__name__
        time.sleep(0.25)
    raise RuntimeError(f"app_not_ready:{last_err}")


class _WebhookRecorder:
    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = int(port)
        self.calls: list[dict[str, Any]] = []
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        recorder = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):  # type: ignore[override]
                size = int(self.headers.get("Content-Length", "0") or 0)
                raw = self.rfile.read(size) if size > 0 else b""
                payload: dict[str, Any] = {}
                try:
                    data = json.loads(raw.decode("utf-8"))
                    if isinstance(data, dict):
                        payload = data
                except Exception:
                    payload = {}
                recorder.calls.append(
                    {
                        "ts": round(time.time(), 3),
                        "path": str(self.path or ""),
                        "payload": payload,
                        "size": len(raw),
                    }
                )
                out = b'{"ok":1}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(out)))
                self.end_headers()
                self.wfile.write(out)

            def log_message(self, format: str, *args: object) -> None:  # noqa: A003
                return

        self._server = ThreadingHTTPServer((self.host, self.port), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server is not None:
            try:
                self._server.shutdown()
            except Exception:
                pass
            try:
                self._server.server_close()
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=2.0)


def _start_app(
    *,
    host: str,
    port: int,
    webhook_url: str,
    cooldown_s: float,
    admin_key: str,
) -> subprocess.Popen:
    env = os.environ.copy()
    env["WRITING_AGENT_USE_OLLAMA"] = "0"
    env["WRITING_AGENT_CITATION_VERIFY_ALERTS"] = "1"
    env["WRITING_AGENT_CITATION_VERIFY_ALERT_MIN_RUNS"] = "1"
    env["WRITING_AGENT_CITATION_VERIFY_ALERT_NOTIFY"] = "1"
    env["WRITING_AGENT_CITATION_VERIFY_ALERT_NOTIFY_COOLDOWN_S"] = str(max(0.2, float(cooldown_s)))
    env["WRITING_AGENT_CITATION_VERIFY_ALERT_WEBHOOK_URL"] = str(webhook_url or "").strip()
    if str(admin_key or "").strip():
        env["WRITING_AGENT_ADMIN_API_KEY"] = str(admin_key).strip()
    cmd = [sys.executable, "-m", "uvicorn", "writing_agent.web.app_v2:app", "--host", host, "--port", str(int(port))]
    return subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _stop_process(proc: subprocess.Popen | None) -> None:
    if proc is None:
        return
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
    except Exception:
        pass
    try:
        proc.wait(timeout=5.0)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _create_doc_id(base_url: str, *, timeout_s: float) -> str:
    req = Request(f"{base_url.rstrip('/')}/", method="GET")
    with urlopen(req, timeout=max(0.2, float(timeout_s))) as resp:
        final_url = str(resp.geturl() or "")
    parts = urlsplit(final_url)
    if not parts.path:
        raise RuntimeError("create_doc_failed:no_redirect")
    doc_id = parts.path.rstrip("/").split("/")[-1]
    if not doc_id:
        raise RuntimeError("create_doc_failed:empty_doc_id")
    return doc_id


def _build_admin_headers(admin_key: str) -> dict[str, str]:
    key = str(admin_key or "").strip()
    if not key:
        return {}
    return {"X-Admin-Key": key}


def _compact_notification(note: dict[str, Any]) -> dict[str, Any]:
    row = note if isinstance(note, dict) else {}
    out: dict[str, Any] = {
        "enabled": bool(row.get("enabled")),
        "webhook_configured": bool(row.get("webhook_configured")),
        "sent": bool(row.get("sent")),
        "channels": row.get("channels") if isinstance(row.get("channels"), list) else [],
        "signature": str(row.get("signature") or ""),
        "event_type": str(row.get("event_type") or ""),
        "status": str(row.get("status") or ""),
        "cooldown_s": float(row.get("cooldown_s") or 0.0),
        "last_sent_at": float(row.get("last_sent_at") or 0.0),
        "suppressed": int(row.get("suppressed") or 0),
        "last_error": str(row.get("last_error") or ""),
        "event_id": str(row.get("event_id") or ""),
        "events_total": int(row.get("events_total") or 0),
    }
    recent = row.get("events_recent")
    items: list[dict[str, Any]] = []
    if isinstance(recent, list):
        for it in recent[-2:]:
            if not isinstance(it, dict):
                continue
            items.append(
                {
                    "id": str(it.get("id") or ""),
                    "ts": float(it.get("ts") or 0.0),
                    "severity": str(it.get("severity") or ""),
                    "event_type": str(it.get("event_type") or ""),
                    "status": str(it.get("status") or ""),
                    "sent": bool(it.get("sent")),
                    "dedupe_hit": bool(it.get("dedupe_hit")),
                    "channels": it.get("channels") if isinstance(it.get("channels"), list) else [],
                }
            )
    out["events_recent"] = items
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Webhook failure/recovery chaos scenario for citation verify alerts.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18110)
    parser.add_argument("--webhook-port", type=int, default=18111)
    parser.add_argument("--cooldown-s", type=float, default=10.0)
    parser.add_argument("--timeout-s", type=float, default=8.0)
    parser.add_argument("--admin-key", default=os.environ.get("WA_ADMIN_KEY", ""))
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    host = str(args.host or "127.0.0.1").strip() or "127.0.0.1"
    port = int(args.port)
    webhook_port = int(args.webhook_port)
    timeout_s = max(0.5, float(args.timeout_s))
    cooldown_s = max(0.2, float(args.cooldown_s))
    admin_key = str(args.admin_key or "").strip()
    base_url = f"http://{host}:{port}"
    webhook_url = f"http://{host}:{webhook_port}/alerts"

    started_ts = time.time()
    proc: subprocess.Popen | None = None
    recorder = _WebhookRecorder(host, webhook_port)
    report: dict[str, Any] = {
        "ok": False,
        "base_url": base_url,
        "webhook_url": webhook_url,
        "started_at": round(started_ts, 3),
        "checks": [],
        "phases": {},
    }
    headers = _build_admin_headers(admin_key)
    try:
        proc = _start_app(host=host, port=port, webhook_url=webhook_url, cooldown_s=cooldown_s, admin_key=admin_key)
        _wait_ready(base_url, timeout_s=timeout_s)

        config_payload = {
            "config": {
                "enabled": True,
                "min_runs": 1,
                "p95_ms": 100,
                "error_rate_per_run": 0.0,
                "cache_delta_hit_rate": 1.0,
            }
        }
        _json_request(
            "POST",
            f"{base_url}/api/metrics/citation_verify/alerts/config",
            body=config_payload,
            headers=headers,
            timeout_s=timeout_s,
        )
        doc_id = _create_doc_id(base_url, timeout_s=timeout_s)
        _json_request(
            "POST",
            f"{base_url}/api/doc/{doc_id}/citations/verify",
            body={"persist": False},
            timeout_s=timeout_s,
        )

        _, body_fail = _json_request("GET", f"{base_url}/api/metrics/citation_verify", timeout_s=timeout_s)
        note_fail = (
            ((body_fail.get("alerts") if isinstance(body_fail.get("alerts"), dict) else {}) or {}).get("notification")
            if isinstance(body_fail, dict)
            else {}
        )
        note_fail = note_fail if isinstance(note_fail, dict) else {}
        report["phases"]["fail"] = _compact_notification(note_fail)

        recorder.start()
        recover_cfg = {
            "config": {
                "enabled": True,
                "min_runs": 1,
                "p95_ms": 60000,
                "error_rate_per_run": 1.0,
                "cache_delta_hit_rate": 0.0,
            }
        }
        _json_request(
            "POST",
            f"{base_url}/api/metrics/citation_verify/alerts/config",
            body=recover_cfg,
            headers=headers,
            timeout_s=timeout_s,
        )
        time.sleep(0.25)
        _, body_recover = _json_request("GET", f"{base_url}/api/metrics/citation_verify", timeout_s=timeout_s)
        note_recover = (
            ((body_recover.get("alerts") if isinstance(body_recover.get("alerts"), dict) else {}) or {}).get("notification")
            if isinstance(body_recover, dict)
            else {}
        )
        note_recover = note_recover if isinstance(note_recover, dict) else {}
        report["phases"]["recover"] = _compact_notification(note_recover)
        report["webhook_calls"] = recorder.calls

        fail_status = str(note_fail.get("status") or "")
        recover_status = str(note_recover.get("status") or "")
        recover_channels = note_recover.get("channels") if isinstance(note_recover.get("channels"), list) else []
        check_rows = [
            {
                "id": "phase_fail_has_webhook_error",
                "ok": fail_status in {"webhook_failed", "suppressed"} or fail_status.startswith("webhook:"),
                "value": fail_status,
            },
            {
                "id": "phase_recover_webhook_sent",
                "ok": "webhook" in [str(x) for x in recover_channels] and recover_status.startswith("http_"),
                "value": {"status": recover_status, "channels": recover_channels},
            },
            {
                "id": "webhook_receiver_got_calls",
                "ok": len(recorder.calls) > 0,
                "value": len(recorder.calls),
            },
        ]
        report["checks"] = check_rows
        report["ok"] = all(bool(row.get("ok")) for row in check_rows)
    except HTTPError as exc:
        report["error"] = f"http_{int(exc.code or 0)}"
    except Exception as exc:
        report["error"] = f"{exc.__class__.__name__}:{exc}"
    finally:
        recorder.stop()
        _stop_process(proc)
        report["ended_at"] = round(time.time(), 3)
        report["duration_s"] = round(report["ended_at"] - report["started_at"], 3)  # type: ignore[operator]

    default_out = Path(".data/out") / f"citation_verify_alert_chaos_{int(time.time())}.json"
    out_path = Path(str(args.out or default_out))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if bool(report.get("ok")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
