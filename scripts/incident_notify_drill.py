#!/usr/bin/env python3
"""Incident Notify Drill command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from aiosmtpd.controller import Controller
from aiosmtpd.handlers import AsyncMessage


def _build_synthetic_incident_report(*, ts: float, level: str = "p1") -> dict[str, Any]:
    incident_id = f"INC-DRILL-{int(ts)}"
    severity = "critical" if str(level).lower() == "p1" else "high"
    return {
        "ok": True,
        "skipped": False,
        "started_at": round(ts - 1.2, 3),
        "ended_at": round(ts, 3),
        "duration_s": 1.2,
        "checks": [],
        "incident": {
            "incident_id": incident_id,
            "title": "Incident notification drill",
            "severity": severity,
            "escalation_level": str(level).lower(),
            "triggered_by": ["drill"],
            "recommended_actions": ["notify_oncall_channel", "open_incident"],
            "owner": "oncall-drill",
            "status": "open",
            "scope": "drill",
            "created_at": round(ts, 3),
            "created_at_iso": "",
            "timeline": [],
            "load_summary": {},
            "slo_observed": {},
            "evidence_paths": {},
        },
        "markdown_path": "",
    }


def _build_synthetic_oncall_roster(*, ts: float, webhook_url: str, email: str) -> dict[str, Any]:
    return {
        "version": 1,
        "source": "incident-notify-drill",
        "updated_at": round(ts, 3),
        "primary": {
            "id": "oncall-drill-primary",
            "name": "On-call Drill Primary",
            "webhook_url": str(webhook_url),
            "slack_webhook_url": "",
            "feishu_webhook_url": "",
            "email": [str(email)],
        },
    }


def _safe_json_load(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return raw if isinstance(raw, dict) else None


class _NotifyReceiver:
    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = int(port)
        self.calls: list[dict[str, Any]] = []
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        receiver = self

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
                receiver.calls.append(
                    {
                        "ts": round(time.time(), 3),
                        "path": str(self.path or ""),
                        "payload": payload,
                        "headers": {
                            "x_wa_timestamp": str(self.headers.get("X-WA-Timestamp") or ""),
                            "x_wa_signature": str(self.headers.get("X-WA-Signature") or ""),
                        },
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


class _SMTPMessageHandler(AsyncMessage):
    def __init__(self, sink: list[dict[str, Any]]) -> None:
        super().__init__()
        self._sink = sink

    async def handle_message(self, message):  # type: ignore[override]
        sender = str(message.get("From") or "")
        recipients = str(message.get("To") or "")
        body = str(message.as_string() or "")
        self._sink.append(
            {
                "ts": round(time.time(), 3),
                "mailfrom": sender,
                "rcpttos": [x.strip() for x in recipients.split(",") if x.strip()],
                "size": len(body),
                "body_preview": body[:800],
            }
        )


class _SMTPReceiver:
    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = int(port)
        self.calls: list[dict[str, Any]] = []
        self._controller: Controller | None = None

    def start(self) -> None:
        handler = _SMTPMessageHandler(self.calls)
        self._controller = Controller(handler, hostname=self.host, port=self.port)
        self._controller.start()

    def stop(self) -> None:
        if self._controller is not None:
            try:
                self._controller.stop()
            except Exception:
                pass


def _latest_call(calls: list[dict[str, Any]], path: str) -> dict[str, Any] | None:
    rows = [row for row in calls if str(row.get("path") or "") == str(path)]
    if not rows:
        return None
    return rows[-1]


def _run_notify(
    *,
    report_path: Path,
    oncall_roster_path: Path,
    host: str,
    port: int,
    signing_key: str,
    out_path: Path,
    timeout_s: float,
    with_email: bool,
    email_port: int,
) -> subprocess.CompletedProcess[str]:
    base = f"http://{host}:{int(port)}"
    cmd = [
        sys.executable,
        "scripts/incident_notify.py",
        "--incident-report",
        report_path.as_posix(),
        "--webhook-url",
        f"{base}/webhook",
        "--slack-webhook-url",
        f"{base}/slack",
        "--feishu-webhook-url",
        f"{base}/feishu",
        "--oncall-roster",
        oncall_roster_path.as_posix(),
        "--prefer-oncall-roster",
        "1",
        "--signing-key",
        signing_key,
        "--strict",
        "--retries",
        "1",
        "--retry-backoff-s",
        "0",
        "--timeout-s",
        str(max(0.2, float(timeout_s))),
        "--out",
        out_path.as_posix(),
    ]
    if bool(with_email):
        cmd.extend(
            [
                "--email-to",
                "oncall@example.local",
                "--email-from",
                "writing-agent@example.local",
                "--smtp-host",
                host,
                "--smtp-port",
                str(int(email_port)),
                "--smtp-starttls",
                "0",
            ]
        )
    return subprocess.run(cmd, check=False, text=True, capture_output=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Local end-to-end drill for incident notification channels.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18140)
    parser.add_argument("--with-email", action="store_true")
    parser.add_argument("--signing-key", default="drill-secret")
    parser.add_argument("--timeout-s", type=float, default=5.0)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    started = time.time()
    host = str(args.host or "127.0.0.1").strip() or "127.0.0.1"
    port = int(args.port)
    with_email = bool(args.with_email)
    email_port = int(port) + 1
    signing_key = str(args.signing_key or "").strip() or "drill-secret"
    timeout_s = max(0.2, float(args.timeout_s))

    ts = int(time.time())
    incident_report_path = Path(".data/out") / f"incident_report_drill_{ts}.json"
    notify_out_path = Path(".data/out") / f"incident_notify_drill_notify_{ts}.json"
    roster_path = Path(".data/out") / f"oncall_roster_drill_{ts}.json"
    incident_report_path.parent.mkdir(parents=True, exist_ok=True)

    receiver = _NotifyReceiver(host, port)
    smtp_receiver: _SMTPReceiver | None = None
    report: dict[str, Any] = {
        "ok": False,
        "started_at": round(started, 3),
        "host": host,
        "port": port,
        "with_email": with_email,
        "smtp_port": email_port if with_email else 0,
        "incident_report_path": incident_report_path.as_posix(),
        "incident_notify_report_path": notify_out_path.as_posix(),
        "oncall_roster_path": roster_path.as_posix(),
        "checks": [],
        "calls": [],
    }
    proc: subprocess.CompletedProcess[str] | None = None

    try:
        synthetic = _build_synthetic_incident_report(ts=time.time(), level="p1")
        incident_report_path.write_text(json.dumps(synthetic, ensure_ascii=False, indent=2), encoding="utf-8")
        roster_payload = _build_synthetic_oncall_roster(
            ts=time.time(),
            webhook_url=f"http://{host}:{int(port)}/oncall-webhook",
            email="oncall@example.local",
        )
        roster_path.write_text(json.dumps(roster_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        receiver.start()
        if with_email:
            smtp_receiver = _SMTPReceiver(host, email_port)
            smtp_receiver.start()
        proc = _run_notify(
            report_path=incident_report_path,
            oncall_roster_path=roster_path,
            host=host,
            port=port,
            signing_key=signing_key,
            out_path=notify_out_path,
            timeout_s=timeout_s,
            with_email=with_email,
            email_port=email_port,
        )
        time.sleep(0.15)

        notify_report = _safe_json_load(notify_out_path) or {}
        channels = notify_report.get("channels") if isinstance(notify_report.get("channels"), list) else []

        webhook_call = _latest_call(receiver.calls, "/oncall-webhook") or _latest_call(receiver.calls, "/webhook")
        slack_call = _latest_call(receiver.calls, "/slack")
        feishu_call = _latest_call(receiver.calls, "/feishu")
        email_calls = list((smtp_receiver.calls if smtp_receiver is not None else []))
        expected_channels = 4 if with_email else 3
        oncall_roster_state = notify_report.get("oncall_roster") if isinstance(notify_report.get("oncall_roster"), dict) else {}
        checks = [
            {
                "id": "incident_notify_exit_zero",
                "ok": (proc.returncode == 0 if proc is not None else False),
                "value": int(proc.returncode if proc is not None else -1),
            },
            {
                "id": "incident_notify_report_ok",
                "ok": bool(notify_report.get("ok")),
                "value": bool(notify_report.get("ok")),
            },
            {
                "id": "notify_channels_three",
                "ok": len(channels) >= expected_channels,
                "value": len(channels),
            },
            {
                "id": "receiver_oncall_webhook_called",
                "ok": isinstance(webhook_call, dict),
                "value": bool(isinstance(webhook_call, dict)),
            },
            {
                "id": "receiver_slack_called",
                "ok": isinstance(slack_call, dict),
                "value": bool(isinstance(slack_call, dict)),
            },
            {
                "id": "receiver_feishu_called",
                "ok": isinstance(feishu_call, dict),
                "value": bool(isinstance(feishu_call, dict)),
            },
            {
                "id": "webhook_signature_present",
                "ok": bool(((webhook_call or {}).get("headers") if isinstance(webhook_call, dict) else {}).get("x_wa_signature")),
                "value": str(((webhook_call or {}).get("headers") if isinstance(webhook_call, dict) else {}).get("x_wa_signature") or ""),
            },
            {
                "id": "slack_payload_text",
                "ok": isinstance(((slack_call or {}).get("payload") if isinstance(slack_call, dict) else {}).get("text"), str),
                "value": ((slack_call or {}).get("payload") if isinstance(slack_call, dict) else {}).get("text", ""),
            },
            {
                "id": "feishu_payload_shape",
                "ok": str(((feishu_call or {}).get("payload") if isinstance(feishu_call, dict) else {}).get("msg_type") or "") == "text",
                "value": ((feishu_call or {}).get("payload") if isinstance(feishu_call, dict) else {}).get("msg_type", ""),
            },
            {
                "id": "oncall_roster_loaded",
                "ok": bool(oncall_roster_state.get("loaded")),
                "value": bool(oncall_roster_state.get("loaded")),
            },
            {
                "id": "oncall_roster_used",
                "ok": bool(oncall_roster_state.get("used")),
                "value": bool(oncall_roster_state.get("used")),
            },
        ]
        if with_email:
            checks.append(
                {
                    "id": "receiver_email_called",
                    "ok": len(email_calls) > 0,
                    "value": len(email_calls),
                }
            )
        report["checks"] = checks
        report["ok"] = all(bool(row.get("ok")) for row in checks)
        report["calls"] = receiver.calls
        report["email_calls"] = email_calls
        report["notify_report"] = notify_report
        report["notify_stdout"] = proc.stdout[-4000:] if isinstance(proc.stdout, str) else ""
        report["notify_stderr"] = proc.stderr[-4000:] if isinstance(proc.stderr, str) else ""
    except Exception as exc:
        report["error"] = f"{exc.__class__.__name__}:{exc}"
    finally:
        receiver.stop()
        if smtp_receiver is not None:
            smtp_receiver.stop()
        report["ended_at"] = round(time.time(), 3)
        report["duration_s"] = round(float(report["ended_at"]) - float(report["started_at"]), 3)

    out_path = Path(str(args.out or Path(".data/out") / f"incident_notify_drill_{int(time.time())}.json"))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if bool(report.get("ok")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
