#!/usr/bin/env python3
"""Create Incident Report command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
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


def _latest_report(pattern: str) -> Path | None:
    rows = sorted(Path(".").glob(pattern), key=lambda p: p.stat().st_mtime if p.exists() else 0.0)
    if not rows:
        return None
    return rows[-1]


def _normalize_events(raw: dict[str, Any] | list[Any] | None) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [row for row in raw if isinstance(row, dict)]
    if isinstance(raw, dict):
        events = raw.get("events")
        if isinstance(events, list):
            return [row for row in events if isinstance(row, dict)]
    return []


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _first_non_empty(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _latest_event_text(events: list[dict[str, Any]], key: str) -> str:
    target = str(key or "").strip()
    if not target:
        return ""
    for row in reversed(events):
        text = str((row if isinstance(row, dict) else {}).get(target) or "").strip()
        if text:
            return text
    return ""


def _extract_correlation(raw: dict[str, Any] | None) -> tuple[str, str]:
    node = raw if isinstance(raw, dict) else {}
    corr_node = node.get("correlation") if isinstance(node.get("correlation"), dict) else {}
    incident_node = node.get("incident") if isinstance(node.get("incident"), dict) else {}
    observed = node.get("observed") if isinstance(node.get("observed"), dict) else {}
    last_event = observed.get("last_event") if isinstance(observed.get("last_event"), dict) else {}
    correlation_id = _first_non_empty(
        corr_node.get("correlation_id"),
        incident_node.get("correlation_id"),
        last_event.get("correlation_id"),
    )
    release_candidate_id = _first_non_empty(
        corr_node.get("release_candidate_id"),
        incident_node.get("release_candidate_id"),
        last_event.get("release_candidate_id"),
    )
    if not release_candidate_id and correlation_id:
        release_candidate_id = correlation_id
    if not correlation_id and release_candidate_id:
        correlation_id = release_candidate_id
    return (correlation_id, release_candidate_id)


def _pick_incident_severity(level: str, fallback: str = "") -> str:
    row = str(fallback or "").strip().lower()
    if row in {"critical", "high", "medium", "low"}:
        return row
    mapped = {"p1": "critical", "p2": "high", "none": "low"}
    return mapped.get(str(level or "").strip().lower(), "medium")


def _to_iso(ts: float) -> str:
    if ts <= 0:
        return ""
    return datetime.fromtimestamp(float(ts), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _build_timeline(events: list[dict[str, Any]], *, limit: int = 12) -> list[dict[str, Any]]:
    rows = sorted(events, key=lambda row: _safe_float(row.get("ts"), 0.0))
    picked = rows[-max(1, int(limit)) :]
    out: list[dict[str, Any]] = []
    for row in picked:
        out.append(
            {
                "id": str(row.get("id") or ""),
                "ts": _safe_float(row.get("ts"), 0.0),
                "ts_iso": _to_iso(_safe_float(row.get("ts"), 0.0)),
                "severity": str(row.get("severity") or ""),
                "event_type": str(row.get("event_type") or ""),
                "status": str(row.get("status") or ""),
                "channels": [
                    str(x).strip()
                    for x in (row.get("channels") if isinstance(row.get("channels"), list) else [])
                    if str(x).strip()
                ],
                "triggered_rules": [
                    str(x).strip()
                    for x in (row.get("triggered_rules") if isinstance(row.get("triggered_rules"), list) else [])
                    if str(x).strip()
                ],
                "correlation_id": str(row.get("correlation_id") or ""),
                "release_candidate_id": str(row.get("release_candidate_id") or ""),
            }
        )
    return out


def _render_markdown(payload: dict[str, Any]) -> str:
    timeline = payload.get("timeline") if isinstance(payload.get("timeline"), list) else []
    actions = payload.get("recommended_actions") if isinstance(payload.get("recommended_actions"), list) else []
    evidence = payload.get("evidence_paths") if isinstance(payload.get("evidence_paths"), dict) else {}
    load_summary = payload.get("load_summary") if isinstance(payload.get("load_summary"), dict) else {}
    slo_observed = payload.get("slo_observed") if isinstance(payload.get("slo_observed"), dict) else {}
    lines: list[str] = []
    lines.append(f"# Incident Report: {payload.get('incident_id', '')}")
    lines.append("")
    lines.append(f"- Title: {payload.get('title', '')}")
    lines.append(f"- Severity: {payload.get('severity', '')}")
    lines.append(f"- Escalation Level: {payload.get('escalation_level', '')}")
    lines.append(f"- Triggered By: {', '.join(payload.get('triggered_by', [])) if isinstance(payload.get('triggered_by'), list) else ''}")
    lines.append(f"- Owner: {payload.get('owner', '')}")
    lines.append(f"- Created At (UTC): {payload.get('created_at_iso', '')}")
    lines.append(f"- Correlation ID: {payload.get('correlation_id', '')}")
    lines.append(f"- Release Candidate ID: {payload.get('release_candidate_id', '')}")
    lines.append("")
    lines.append("## Current Status")
    lines.append(f"- Status: {payload.get('status', '')}")
    lines.append(f"- Scope: {payload.get('scope', '')}")
    lines.append("")
    lines.append("## Key Metrics")
    if load_summary:
        lines.append(f"- Load success_rate: {load_summary.get('success_rate', '')}")
        latency = load_summary.get("latency_ms") if isinstance(load_summary.get("latency_ms"), dict) else {}
        lines.append(f"- Load latency_p95_ms: {latency.get('p95', '')}")
        lines.append(f"- Load degraded_rate: {load_summary.get('degraded_rate', '')}")
    if slo_observed:
        lines.append(f"- SLO success_rate: {slo_observed.get('success_rate', '')}")
        lines.append(f"- SLO latency_p95_ms: {slo_observed.get('latency_p95_ms', '')}")
        lines.append(f"- SLO degraded_rate: {slo_observed.get('degraded_rate', '')}")
    lines.append("")
    lines.append("## Recommended Actions")
    if actions:
        for item in actions:
            lines.append(f"- [ ] {str(item)}")
    else:
        lines.append("- [ ] Collect additional telemetry and confirm user impact")
        lines.append("- [ ] Notify on-call engineer and set incident commander")
    lines.append("")
    lines.append("## Timeline")
    if timeline:
        lines.append("| Time (UTC) | Severity | Event | Status | Event ID |")
        lines.append("|---|---|---|---|---|")
        for row in timeline:
            lines.append(
                f"| {row.get('ts_iso', '')} | {row.get('severity', '')} | {row.get('event_type', '')} | {row.get('status', '')} | {row.get('id', '')} |"
            )
    else:
        lines.append("- No recent alert events were found in the selected window.")
    lines.append("")
    lines.append("## Evidence")
    for key in ["escalation_report", "rollout_report", "slo_report", "load_report", "events_file"]:
        lines.append(f"- {key}: {evidence.get(key, '')}")
    lines.append("")
    lines.append("## Follow-up")
    lines.append("- [ ] Confirm rollback decision and release channel state")
    lines.append("- [ ] Add root-cause notes and corrective actions")
    lines.append("- [ ] Link this report in CHANGES.md or incident tracker")
    lines.append("")
    return "\n".join(lines).strip() + "\n"


def _check_row(*, check_id: str, ok: bool, value: Any, expect: str, mode: str = "enforce") -> dict[str, Any]:
    return {
        "id": str(check_id),
        "ok": bool(ok),
        "value": value,
        "expect": str(expect),
        "mode": str(mode or "enforce"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate incident report from escalation/SLO/load/alert artifacts.")
    parser.add_argument("--escalation-report", default="")
    parser.add_argument("--rollout-report", default="")
    parser.add_argument("--slo-report", default="")
    parser.add_argument("--load-report", default="")
    parser.add_argument("--events-file", default=".data/citation_verify_alert_events.json")
    parser.add_argument("--title", default="")
    parser.add_argument("--owner", default="oncall")
    parser.add_argument("--severity", default="")
    parser.add_argument("--scope", default="citation_verify metrics and alert channel")
    parser.add_argument("--status", default="open")
    parser.add_argument("--correlation-id", default="")
    parser.add_argument("--release-candidate-id", default="")
    parser.add_argument("--only-when-escalated", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--out-dir", default=".data/out")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    started = time.time()
    checks: list[dict[str, Any]] = []

    escalation_path = (
        Path(str(args.escalation_report))
        if str(args.escalation_report).strip()
        else _latest_report(".data/out/alert_escalation_*.json")
    )
    rollout_path = (
        Path(str(args.rollout_report))
        if str(args.rollout_report).strip()
        else _latest_report(".data/out/release_rollout_executor_*.json")
    )
    slo_path = Path(str(args.slo_report)) if str(args.slo_report).strip() else _latest_report(".data/out/slo_guard_*.json")
    load_path = (
        Path(str(args.load_report))
        if str(args.load_report).strip()
        else _latest_report(".data/out/citation_verify_load_probe_*.json")
    )
    events_path = Path(str(args.events_file))

    escalation_raw = _load_json(escalation_path) if isinstance(escalation_path, Path) else None
    rollout_raw = _load_json(rollout_path) if isinstance(rollout_path, Path) else None
    slo_raw = _load_json(slo_path) if isinstance(slo_path, Path) else None
    load_raw = _load_json(load_path) if isinstance(load_path, Path) else None
    events_raw = _load_json(events_path)
    events = _normalize_events(events_raw)

    checks.append(
        _check_row(
            check_id="escalation_report_loaded",
            ok=isinstance(escalation_raw, dict),
            value=escalation_path.as_posix() if isinstance(escalation_path, Path) else "",
            expect="latest alert escalation report exists",
            mode="enforce" if bool(args.strict) else "warn",
        )
    )
    checks.append(
        _check_row(
            check_id="events_file_loaded",
            ok=events_raw is not None,
            value=events_path.as_posix(),
            expect="events file exists and valid json",
            mode="warn",
        )
    )
    checks.append(
        _check_row(
            check_id="rollout_report_loaded",
            ok=isinstance(rollout_raw, dict),
            value=rollout_path.as_posix() if isinstance(rollout_path, Path) else "",
            expect="latest rollout executor report exists",
            mode="warn",
        )
    )

    escalation_node = escalation_raw.get("escalation") if isinstance(escalation_raw, dict) and isinstance(escalation_raw.get("escalation"), dict) else {}
    level = str(escalation_node.get("level") or "none").strip().lower()
    escalation_severity = str(escalation_node.get("severity") or "").strip().lower()
    triggered_by = escalation_node.get("triggered_by") if isinstance(escalation_node.get("triggered_by"), list) else []
    recommended_actions = escalation_node.get("actions") if isinstance(escalation_node.get("actions"), list) else []
    should_skip = bool(args.only_when_escalated and level == "none")
    rollout_corr, rollout_candidate = _extract_correlation(rollout_raw if isinstance(rollout_raw, dict) else None)
    escalation_corr, escalation_candidate = _extract_correlation(escalation_raw if isinstance(escalation_raw, dict) else None)
    event_corr = _latest_event_text(events, "correlation_id")
    event_candidate = _latest_event_text(events, "release_candidate_id")
    explicit_corr = str(args.correlation_id or "").strip()
    explicit_candidate = str(args.release_candidate_id or "").strip()
    correlation_id = _first_non_empty(
        explicit_corr,
        explicit_candidate,
        rollout_corr,
        escalation_corr,
        event_corr,
    )
    release_candidate_id = _first_non_empty(
        explicit_candidate,
        explicit_corr,
        rollout_candidate,
        escalation_candidate,
        event_candidate,
        correlation_id,
    )
    if not release_candidate_id and correlation_id:
        release_candidate_id = correlation_id
    if not correlation_id and release_candidate_id:
        correlation_id = release_candidate_id
    checks.append(
        _check_row(
            check_id="escalation_present_for_incident",
            ok=(not bool(args.only_when_escalated)) or (level != "none"),
            value=level,
            expect="when only-when-escalated=true, level must not be none",
            mode="warn",
        )
    )
    checks.append(
        _check_row(
            check_id="correlation_context_available",
            ok=bool(correlation_id or release_candidate_id),
            value={
                "correlation_id": correlation_id,
                "release_candidate_id": release_candidate_id,
            },
            expect="incident report should include at least one correlation identifier",
            mode="warn",
        )
    )
    source_corr_values = [val for val in [rollout_corr, escalation_corr, event_corr] if str(val or "").strip()]
    source_candidate_values = [
        val for val in [rollout_candidate, escalation_candidate, event_candidate] if str(val or "").strip()
    ]
    checks.append(
        _check_row(
            check_id="correlation_id_sources_consistent",
            ok=(len(set(source_corr_values)) <= 1),
            value={"source_values": source_corr_values},
            expect="rollout/escalation/event correlation_id values should be consistent when present",
            mode="enforce" if bool(args.strict and len(source_corr_values) >= 2) else "warn",
        )
    )
    checks.append(
        _check_row(
            check_id="release_candidate_id_sources_consistent",
            ok=(len(set(source_candidate_values)) <= 1),
            value={"source_values": source_candidate_values},
            expect="rollout/escalation/event release_candidate_id values should be consistent when present",
            mode="enforce" if bool(args.strict and len(source_candidate_values) >= 2) else "warn",
        )
    )

    ended = time.time()
    if should_skip:
        report = {
            "ok": True,
            "skipped": True,
            "reason": "no_escalation",
            "started_at": round(started, 3),
            "ended_at": round(ended, 3),
            "duration_s": round(ended - started, 3),
            "checks": checks,
            "paths": {
                "escalation_report": escalation_path.as_posix() if isinstance(escalation_path, Path) else "",
                "rollout_report": rollout_path.as_posix() if isinstance(rollout_path, Path) else "",
                "slo_report": slo_path.as_posix() if isinstance(slo_path, Path) else "",
                "load_report": load_path.as_posix() if isinstance(load_path, Path) else "",
                "events_file": events_path.as_posix(),
            },
            "correlation": {
                "correlation_id": correlation_id,
                "release_candidate_id": release_candidate_id,
            },
            "incident": {},
        }
        out_path = Path(str(args.out or Path(str(args.out_dir)) / f"incident_report_{int(ended)}.json"))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    timeline = _build_timeline(events, limit=12)
    incident_id = f"INC-{int(ended)}"
    severity = _pick_incident_severity(level, fallback=str(args.severity or escalation_severity))
    title = str(args.title or "").strip() or f"Citation Verify escalation {level.upper() if level else 'NONE'}"

    load_summary = load_raw.get("summary") if isinstance(load_raw, dict) and isinstance(load_raw.get("summary"), dict) else {}
    slo_observed = slo_raw.get("observed") if isinstance(slo_raw, dict) and isinstance(slo_raw.get("observed"), dict) else {}

    incident_payload = {
        "incident_id": incident_id,
        "title": title,
        "severity": severity,
        "escalation_level": level,
        "correlation_id": correlation_id,
        "release_candidate_id": release_candidate_id,
        "triggered_by": [str(x).strip() for x in triggered_by if str(x).strip()],
        "recommended_actions": [str(x).strip() for x in recommended_actions if str(x).strip()],
        "owner": str(args.owner),
        "status": str(args.status),
        "scope": str(args.scope),
        "created_at": round(ended, 3),
        "created_at_iso": _to_iso(ended),
        "timeline": timeline,
        "load_summary": load_summary,
        "slo_observed": slo_observed,
        "evidence_paths": {
            "escalation_report": escalation_path.as_posix() if isinstance(escalation_path, Path) else "",
            "rollout_report": rollout_path.as_posix() if isinstance(rollout_path, Path) else "",
            "slo_report": slo_path.as_posix() if isinstance(slo_path, Path) else "",
            "load_report": load_path.as_posix() if isinstance(load_path, Path) else "",
            "events_file": events_path.as_posix(),
        },
    }

    markdown = _render_markdown(incident_payload)
    out_dir = Path(str(args.out_dir))
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"incident_report_{int(ended)}.md"
    md_path.write_text(markdown, encoding="utf-8")

    checks.append(
        _check_row(
            check_id="incident_markdown_written",
            ok=md_path.exists(),
            value=md_path.as_posix(),
            expect="incident markdown file created",
            mode="enforce",
        )
    )
    checks.append(
        _check_row(
            check_id="timeline_available",
            ok=len(timeline) > 0,
            value=len(timeline),
            expect=">0 timeline rows",
            mode="warn",
        )
    )

    enforce_rows = [row for row in checks if str(row.get("mode") or "enforce") == "enforce"]
    ok = all(bool(row.get("ok")) for row in enforce_rows)

    report = {
        "ok": bool(ok),
        "skipped": False,
        "started_at": round(started, 3),
        "ended_at": round(ended, 3),
        "duration_s": round(ended - started, 3),
        "checks": checks,
        "correlation": {
            "correlation_id": correlation_id,
            "release_candidate_id": release_candidate_id,
        },
        "incident": incident_payload,
        "markdown_path": md_path.as_posix(),
    }
    out_path = Path(str(args.out or out_dir / f"incident_report_{int(ended)}.json"))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if bool(report.get("ok")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
