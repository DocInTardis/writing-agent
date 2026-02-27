#!/usr/bin/env python3
"""Capacity Guard command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import argparse
import copy
import fnmatch
import json
import os
import statistics
import time
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return raw if isinstance(raw, dict) else None


def _latest_report(pattern: str) -> Path | None:
    rows = sorted(Path(".").glob(pattern), key=lambda p: p.stat().st_mtime if p.exists() else 0.0)
    if not rows:
        return None
    return rows[-1]


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


def _safe_mode(value: Any, default: str = "warn") -> str:
    text = str(value or "").strip().lower()
    if text in {"warn", "enforce"}:
        return text
    return str(default or "warn")


def _normalize_path_text(path_text: str) -> str:
    text = str(path_text or "").strip()
    if not text:
        return ""
    try:
        return Path(text).resolve().as_posix()
    except Exception:
        return Path(text).as_posix()


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_profile(value: Any) -> str:
    text = _normalize_text(value).lower()
    alias = {
        "production": "prod",
        "stage": "staging",
        "development": "dev",
    }
    return alias.get(text, text)


def _deep_merge_dict(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge_dict(out.get(key) if isinstance(out.get(key), dict) else {}, value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def _check_row(check_id: str, ok: bool, value: Any, expect: str, mode: str = "enforce") -> dict[str, Any]:
    return {
        "id": str(check_id),
        "ok": bool(ok),
        "value": value,
        "expect": str(expect),
        "mode": str(mode or "enforce"),
    }


def _extract_report_ts(report_raw: dict[str, Any], fallback_ts: float) -> float:
    for key in ("ended_at", "ts", "generated_at", "started_at"):
        value = _safe_float(report_raw.get(key), 0.0)
        if value > 0:
            return value
    return float(fallback_ts)


def _report_age_s(*, report_path: Path | None, report_raw: dict[str, Any] | None, now_ts: float) -> float:
    if report_path is None or not report_path.exists():
        return float("inf")
    fallback_ts = report_path.stat().st_mtime
    if isinstance(report_raw, dict):
        ts = _extract_report_ts(report_raw, fallback_ts=fallback_ts)
    else:
        ts = fallback_ts
    return max(0.0, float(now_ts) - float(ts))


def _calc_effective_rps(load_summary: dict[str, Any]) -> float:
    requests = _safe_float(load_summary.get("requests"), 0.0)
    duration_s = _safe_float(load_summary.get("duration_s"), 0.0)
    if requests <= 0 or duration_s <= 0:
        return 0.0
    return requests / duration_s


def _median(values: list[float]) -> float:
    rows = [float(x) for x in values if float(x) >= 0.0]
    if not rows:
        return 0.0
    return float(statistics.median(rows))


def _load_row_from_report(*, report_path: Path, report_raw: dict[str, Any]) -> dict[str, Any]:
    summary = report_raw.get("summary") if isinstance(report_raw.get("summary"), dict) else {}
    latency = summary.get("latency_ms") if isinstance(summary.get("latency_ms"), dict) else {}
    fallback_ts = report_path.stat().st_mtime if report_path.exists() else 0.0
    ts = _extract_report_ts(report_raw, fallback_ts=fallback_ts)
    return {
        "path": report_path.as_posix(),
        "ts": ts,
        "effective_rps": _calc_effective_rps(summary),
        "success_rate": _safe_float(summary.get("success_rate"), 0.0),
        "degraded_rate": _safe_float(summary.get("degraded_rate"), 0.0),
        "p95_ms": _safe_float(latency.get("p95"), 0.0),
    }


def _extract_load_history(pattern: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(Path(".").glob(pattern), key=lambda p: p.stat().st_mtime if p.exists() else 0.0):
        raw = _load_json(path)
        if not isinstance(raw, dict):
            continue
        rows.append(_load_row_from_report(report_path=path, report_raw=raw))
    rows.sort(key=lambda row: _safe_float(row.get("ts"), 0.0))
    return rows


def _resolve_release_context(
    *,
    release_tier: str,
    release_branch: str,
    runtime_env: str,
) -> dict[str, str]:
    tier = _normalize_text(release_tier) or _normalize_text(os.environ.get("WA_CAPACITY_RELEASE_TIER"))
    branch = (
        _normalize_text(release_branch)
        or _normalize_text(os.environ.get("WA_CAPACITY_RELEASE_BRANCH"))
        or _normalize_text(os.environ.get("GITHUB_REF_NAME"))
        or _normalize_text(os.environ.get("CI_COMMIT_REF_NAME"))
    )
    env_name = _normalize_text(runtime_env) or _normalize_text(os.environ.get("WA_RUNTIME_ENV"))
    return {
        "release_tier": tier,
        "release_branch": branch,
        "runtime_env": env_name,
    }


def _derive_capacity_profile(
    *,
    capacity_profile: str,
    release_context: dict[str, str],
) -> tuple[str, str]:
    explicit = _normalize_profile(capacity_profile)
    if explicit:
        return explicit, "explicit"

    env_profile = _normalize_profile(os.environ.get("WA_CAPACITY_PROFILE"))
    if env_profile:
        return env_profile, "env:WA_CAPACITY_PROFILE"

    tier = _normalize_profile(release_context.get("release_tier"))
    if tier:
        return tier, "release_tier"

    runtime_env = _normalize_profile(release_context.get("runtime_env"))
    if runtime_env:
        return runtime_env, "runtime_env"

    branch = _normalize_text(release_context.get("release_branch")).lower()
    if branch in {"main", "master"} or branch.startswith("release/") or branch.startswith("hotfix/"):
        return "prod", "release_branch"
    if branch.startswith("staging/") or branch.startswith("stage/"):
        return "staging", "release_branch"
    if branch.startswith("feature/"):
        return "dev", "release_branch"
    return "default", "default"


def _resolve_citation_metrics_for_profile(
    *,
    policy_raw: dict[str, Any],
    capacity_profile: str,
    release_context: dict[str, str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    root = policy_raw.get("citation_metrics") if isinstance(policy_raw.get("citation_metrics"), dict) else {}
    base = {k: copy.deepcopy(v) for k, v in root.items() if str(k) != "profile_overrides"}
    overrides = root.get("profile_overrides") if isinstance(root.get("profile_overrides"), dict) else {}

    profile_requested, profile_source = _derive_capacity_profile(
        capacity_profile=capacity_profile,
        release_context=release_context,
    )
    profile_override = overrides.get(profile_requested) if isinstance(overrides.get(profile_requested), dict) else {}
    profile_resolved = profile_requested
    if not profile_override and profile_requested != "default":
        default_override = overrides.get("default") if isinstance(overrides.get("default"), dict) else {}
        if default_override:
            profile_override = default_override
            profile_resolved = "default"
            profile_source = f"{profile_source}->default"

    merged = _deep_merge_dict(base, profile_override if isinstance(profile_override, dict) else {})
    info = {
        "requested": profile_requested,
        "resolved": profile_resolved,
        "source": profile_source,
        "override_applied": bool(profile_override),
    }
    return merged, info


def _headroom_history_mode_override(
    *,
    node: dict[str, Any],
    release_context: dict[str, str],
) -> tuple[str, str]:
    tier = _normalize_text(release_context.get("release_tier"))
    runtime_env = _normalize_text(release_context.get("runtime_env"))
    branch = _normalize_text(release_context.get("release_branch"))

    mode_by_release_tier = node.get("mode_by_release_tier") if isinstance(node.get("mode_by_release_tier"), dict) else {}
    if tier:
        tier_mode = _safe_mode(mode_by_release_tier.get(tier), "")
        if tier_mode in {"warn", "enforce"}:
            return tier_mode, f"mode_by_release_tier:{tier}"

    mode_by_runtime_env = node.get("mode_by_runtime_env") if isinstance(node.get("mode_by_runtime_env"), dict) else {}
    if runtime_env:
        env_mode = _safe_mode(mode_by_runtime_env.get(runtime_env), "")
        if env_mode in {"warn", "enforce"}:
            return env_mode, f"mode_by_runtime_env:{runtime_env}"

    mode_by_branch_pattern = node.get("mode_by_branch_pattern")
    if branch and isinstance(mode_by_branch_pattern, list):
        for item in mode_by_branch_pattern:
            if not isinstance(item, dict):
                continue
            pattern = _normalize_text(item.get("pattern"))
            if not pattern:
                continue
            if fnmatch.fnmatch(branch, pattern):
                branch_mode = _safe_mode(item.get("mode"), "")
                if branch_mode in {"warn", "enforce"}:
                    return branch_mode, f"mode_by_branch_pattern:{pattern}"
    return "", ""


def _load_targets(
    policy_raw: dict[str, Any],
    quick: bool,
    *,
    citation_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = (
        citation_metrics
        if isinstance(citation_metrics, dict)
        else (policy_raw.get("citation_metrics") if isinstance(policy_raw.get("citation_metrics"), dict) else {})
    )
    target_peak_rps = _safe_float(root.get("target_peak_rps"), 20.0)
    required_headroom_ratio = _safe_float(root.get("required_headroom_ratio"), 1.2)
    max_latency_p95_ms = _safe_float(root.get("max_latency_p95_ms"), 1200.0)
    max_degraded_rate = _safe_float(root.get("max_degraded_rate"), 0.05)
    min_success_rate = _safe_float(root.get("min_success_rate"), 0.99)
    load_report_max_age_s = _safe_float(root.get("load_report_max_age_s"), 172800.0)
    soak_report_max_age_s = _safe_float(root.get("soak_report_max_age_s"), 604800.0)
    quick_allow_headroom_history_fallback = False

    if quick:
        relax = root.get("quick_relax") if isinstance(root.get("quick_relax"), dict) else {}
        required_headroom_ratio = min(
            required_headroom_ratio,
            _safe_float(relax.get("required_headroom_ratio"), required_headroom_ratio),
        )
        quick_allow_headroom_history_fallback = bool(relax.get("allow_headroom_history_fallback", False))
        max_latency_p95_ms = max(max_latency_p95_ms, _safe_float(relax.get("max_latency_p95_ms"), max_latency_p95_ms))
        max_degraded_rate = max(max_degraded_rate, _safe_float(relax.get("max_degraded_rate"), max_degraded_rate))

    return {
        "target_peak_rps": target_peak_rps,
        "required_headroom_ratio": required_headroom_ratio,
        "max_latency_p95_ms": max_latency_p95_ms,
        "max_degraded_rate": max_degraded_rate,
        "min_success_rate": min_success_rate,
        "load_report_max_age_s": load_report_max_age_s,
        "soak_report_max_age_s": soak_report_max_age_s,
        "quick_allow_headroom_history_fallback": bool(quick_allow_headroom_history_fallback),
    }


def _load_headroom_history_targets(
    policy_raw: dict[str, Any],
    quick: bool,
    release_context: dict[str, str],
    *,
    citation_metrics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = (
        citation_metrics
        if isinstance(citation_metrics, dict)
        else (policy_raw.get("citation_metrics") if isinstance(policy_raw.get("citation_metrics"), dict) else {})
    )
    node = root.get("headroom_history") if isinstance(root.get("headroom_history"), dict) else {}
    override_mode, override_source = _headroom_history_mode_override(node=node, release_context=release_context)
    configured_mode = _safe_mode(override_mode or node.get("mode"), "warn")
    targets: dict[str, Any] = {
        "enabled": bool(node.get("enabled", True)),
        "mode": configured_mode,
        "configured_mode": _safe_mode(node.get("mode"), "warn"),
        "mode_override_source": str(override_source or ""),
        "strict_promote_to_enforce": bool(node.get("strict_promote_to_enforce", True)),
        "promote_when_quick_with_sufficient_history": bool(
            node.get("promote_when_quick_with_sufficient_history", False)
        ),
        "window_runs": max(2, _safe_int(node.get("window_runs"), 4)),
        "min_required_runs": max(2, _safe_int(node.get("min_required_runs"), 3)),
        "allow_insufficient_history": bool(node.get("allow_insufficient_history", True)),
        "max_latest_drop_ratio_to_window_median": max(
            0.0,
            _safe_float(node.get("max_latest_drop_ratio_to_window_median"), 0.12),
        ),
    }
    if quick:
        relax = node.get("quick_relax") if isinstance(node.get("quick_relax"), dict) else {}
        if not str(targets.get("mode_override_source") or "").strip():
            targets["mode"] = _safe_mode(relax.get("mode"), str(targets.get("mode") or "warn"))
        targets["strict_promote_to_enforce"] = bool(
            relax.get("strict_promote_to_enforce", bool(targets.get("strict_promote_to_enforce")))
        )
        targets["promote_when_quick_with_sufficient_history"] = bool(
            relax.get(
                "promote_when_quick_with_sufficient_history",
                bool(targets.get("promote_when_quick_with_sufficient_history")),
            )
        )
        targets["window_runs"] = min(
            int(targets.get("window_runs") or 4),
            max(2, _safe_int(relax.get("window_runs"), int(targets.get("window_runs") or 4))),
        )
        targets["min_required_runs"] = min(
            int(targets.get("min_required_runs") or 3),
            max(2, _safe_int(relax.get("min_required_runs"), int(targets.get("min_required_runs") or 3))),
        )
        targets["allow_insufficient_history"] = bool(
            relax.get("allow_insufficient_history", bool(targets.get("allow_insufficient_history")))
        )
        targets["max_latest_drop_ratio_to_window_median"] = max(
            float(targets.get("max_latest_drop_ratio_to_window_median") or 0.0),
            max(
                0.0,
                _safe_float(
                    relax.get("max_latest_drop_ratio_to_window_median"),
                    float(targets.get("max_latest_drop_ratio_to_window_median") or 0.0),
                ),
            ),
        )
    return targets


def _load_soak_targets(
    policy_raw: dict[str, Any],
    quick: bool,
    *,
    citation_metrics: dict[str, Any] | None = None,
) -> dict[str, float]:
    root = (
        citation_metrics
        if isinstance(citation_metrics, dict)
        else (policy_raw.get("citation_metrics") if isinstance(policy_raw.get("citation_metrics"), dict) else {})
    )
    soak = root.get("soak") if isinstance(root.get("soak"), dict) else {}
    targets = {
        "min_duration_s": _safe_float(soak.get("min_duration_s"), 1200.0),
        "min_window_count": float(_safe_int(soak.get("min_window_count"), 10)),
        "min_success_rate": _safe_float(soak.get("min_success_rate"), 0.995),
        "max_latency_p95_ms": _safe_float(soak.get("max_latency_p95_ms"), 2000.0),
    }
    if quick:
        relax = soak.get("quick_relax") if isinstance(soak.get("quick_relax"), dict) else {}
        targets["min_duration_s"] = min(targets["min_duration_s"], _safe_float(relax.get("min_duration_s"), targets["min_duration_s"]))
        targets["min_window_count"] = min(
            targets["min_window_count"],
            float(_safe_int(relax.get("min_window_count"), int(targets["min_window_count"]))),
        )
        targets["min_success_rate"] = min(
            targets["min_success_rate"],
            _safe_float(relax.get("min_success_rate"), targets["min_success_rate"]),
        )
        targets["max_latency_p95_ms"] = max(
            targets["max_latency_p95_ms"],
            _safe_float(relax.get("max_latency_p95_ms"), targets["max_latency_p95_ms"]),
        )
    return targets


def main() -> int:
    parser = argparse.ArgumentParser(description="Capacity guard using load probe and optional soak report.")
    parser.add_argument("--policy", default="security/capacity_policy.json")
    parser.add_argument("--load-report", default="")
    parser.add_argument("--load-pattern", default=".data/out/citation_verify_load_probe_*.json")
    parser.add_argument("--soak-report", default="")
    parser.add_argument("--capacity-profile", default="")
    parser.add_argument("--release-tier", default="")
    parser.add_argument("--release-branch", default="")
    parser.add_argument("--runtime-env", default="")
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--require-soak", action="store_true")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    started = time.time()
    checks: list[dict[str, Any]] = []

    policy_path = Path(str(args.policy))
    load_path = Path(str(args.load_report)) if str(args.load_report).strip() else _latest_report(str(args.load_pattern))
    soak_path = Path(str(args.soak_report)) if str(args.soak_report).strip() else _latest_report(".data/out/citation_verify_soak_*.json")

    policy_raw = _load_json(policy_path)
    if not isinstance(policy_raw, dict):
        checks.append(_check_row("capacity_policy_loaded", False, False, "capacity policy json exists and valid"))
        report = {
            "ok": False,
            "started_at": round(started, 3),
            "ended_at": round(time.time(), 3),
            "duration_s": round(time.time() - started, 3),
            "checks": checks,
        }
        out_path = Path(str(args.out or Path(".data/out") / f"capacity_guard_{int(time.time())}.json"))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2

    load_raw = _load_json(load_path) if isinstance(load_path, Path) else None
    checks.append(
        _check_row(
            "capacity_load_report_loaded",
            isinstance(load_raw, dict),
            load_path.as_posix() if isinstance(load_path, Path) else "",
            "load probe report exists and valid",
            mode="enforce",
        )
    )
    if not isinstance(load_raw, dict):
        report = {
            "ok": False,
            "started_at": round(started, 3),
            "ended_at": round(time.time(), 3),
            "duration_s": round(time.time() - started, 3),
            "checks": checks,
        }
        out_path = Path(str(args.out or Path(".data/out") / f"capacity_guard_{int(time.time())}.json"))
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 2

    release_context = _resolve_release_context(
        release_tier=str(args.release_tier),
        release_branch=str(args.release_branch),
        runtime_env=str(args.runtime_env),
    )
    citation_metrics_node, profile_info = _resolve_citation_metrics_for_profile(
        policy_raw=policy_raw,
        capacity_profile=str(args.capacity_profile),
        release_context=release_context,
    )
    checks.append(
        _check_row(
            "capacity_profile_resolution",
            True,
            profile_info,
            "capacity profile resolved and profile overrides applied when configured",
            mode="warn",
        )
    )
    targets = _load_targets(policy_raw, quick=bool(args.quick), citation_metrics=citation_metrics_node)
    headroom_history_targets = _load_headroom_history_targets(
        policy_raw,
        quick=bool(args.quick),
        release_context=release_context,
        citation_metrics=citation_metrics_node,
    )
    now_ts = time.time()
    load_summary = load_raw.get("summary") if isinstance(load_raw.get("summary"), dict) else {}
    latency = load_summary.get("latency_ms") if isinstance(load_summary.get("latency_ms"), dict) else {}
    effective_rps = _calc_effective_rps(load_summary)
    target_peak_rps = float(targets.get("target_peak_rps") or 0.0)
    required_headroom_ratio = float(targets.get("required_headroom_ratio") or 0.0)
    headroom_ratio = (effective_rps / target_peak_rps) if target_peak_rps > 0 else 0.0
    success_rate = _safe_float(load_summary.get("success_rate"), 0.0)
    degraded_rate = _safe_float(load_summary.get("degraded_rate"), 0.0)
    p95 = _safe_float(latency.get("p95"), 0.0)
    load_age_s = _report_age_s(report_path=load_path, report_raw=load_raw, now_ts=now_ts)

    checks.append(
        _check_row(
            "capacity_headroom_ratio",
            headroom_ratio >= required_headroom_ratio,
            round(headroom_ratio, 6),
            f">={required_headroom_ratio:.4f} (effective_rps/target_peak_rps)",
            mode="enforce",
        )
    )
    checks.append(
        _check_row(
            "capacity_success_rate",
            success_rate >= float(targets.get("min_success_rate") or 0.0),
            round(success_rate, 6),
            f">={float(targets.get('min_success_rate') or 0.0):.4f}",
            mode="enforce",
        )
    )
    checks.append(
        _check_row(
            "capacity_latency_p95_ms",
            p95 <= float(targets.get("max_latency_p95_ms") or 0.0),
            round(p95, 3),
            f"<={float(targets.get('max_latency_p95_ms') or 0.0):.2f}",
            mode="enforce",
        )
    )
    checks.append(
        _check_row(
            "capacity_degraded_rate",
            degraded_rate <= float(targets.get("max_degraded_rate") or 0.0),
            round(degraded_rate, 6),
            f"<={float(targets.get('max_degraded_rate') or 0.0):.4f}",
            mode="enforce",
        )
    )
    checks.append(
        _check_row(
            "capacity_load_report_fresh",
            load_age_s <= float(targets.get("load_report_max_age_s") or 0.0),
            round(load_age_s, 3),
            f"<={float(targets.get('load_report_max_age_s') or 0.0):.1f}s",
            mode="enforce",
        )
    )

    headroom_history: dict[str, Any] = {
        "enabled": bool(headroom_history_targets.get("enabled", True)),
        "mode": _safe_mode(headroom_history_targets.get("mode"), "warn"),
        "configured_mode": _safe_mode(headroom_history_targets.get("configured_mode"), "warn"),
        "mode_override_source": str(headroom_history_targets.get("mode_override_source") or ""),
        "strict_promote_to_enforce": bool(headroom_history_targets.get("strict_promote_to_enforce", True)),
        "promote_when_quick_with_sufficient_history": bool(
            headroom_history_targets.get("promote_when_quick_with_sufficient_history", False)
        ),
        "window": [],
        "latest_ratio": round(headroom_ratio, 6),
        "median_ratio": round(headroom_ratio, 6),
        "latest_drop_ratio_to_window_median": 0.0,
    }
    if bool(headroom_history_targets.get("enabled", True)) and target_peak_rps > 0:
        history_rows = _extract_load_history(str(args.load_pattern))
        if isinstance(load_path, Path) and isinstance(load_raw, dict):
            load_norm = _normalize_path_text(load_path.as_posix())
            existing_norms = {_normalize_path_text(str(row.get("path") or "")) for row in history_rows}
            if load_norm not in existing_norms:
                history_rows.append(_load_row_from_report(report_path=load_path, report_raw=load_raw))
        history_rows.sort(key=lambda row: _safe_float(row.get("ts"), 0.0))

        configured_history_mode = _safe_mode(headroom_history_targets.get("mode"), "warn")
        source_history_mode = _safe_mode(headroom_history_targets.get("configured_mode"), "warn")
        override_source = str(headroom_history_targets.get("mode_override_source") or "")
        strict_promote = bool(headroom_history_targets.get("strict_promote_to_enforce", True))
        promote_when_quick_with_sufficient_history = bool(
            headroom_history_targets.get("promote_when_quick_with_sufficient_history", False)
        )
        window_runs = max(2, _safe_int(headroom_history_targets.get("window_runs"), 4))
        min_required_runs = max(2, _safe_int(headroom_history_targets.get("min_required_runs"), 3))
        allow_insufficient = bool(headroom_history_targets.get("allow_insufficient_history", True))
        max_latest_drop_ratio = max(
            0.0,
            _safe_float(headroom_history_targets.get("max_latest_drop_ratio_to_window_median"), 0.12),
        )
        window = history_rows[-window_runs:]
        available = len(window)
        enough_history = available >= min_required_runs
        history_mode = configured_history_mode
        promote_reason = ""
        if bool(args.strict) and strict_promote:
            if (not bool(args.quick)) or (bool(args.quick) and promote_when_quick_with_sufficient_history and enough_history):
                history_mode = "enforce"
                promote_reason = "strict_promote_to_enforce"
        checks.append(
            _check_row(
                "capacity_headroom_history_mode",
                True,
                {
                    "configured": configured_history_mode,
                    "base_configured": source_history_mode,
                    "override_source": override_source,
                    "effective": history_mode,
                    "strict": bool(args.strict),
                    "quick": bool(args.quick),
                    "promoted": bool(history_mode == "enforce" and configured_history_mode != "enforce"),
                    "promote_reason": promote_reason,
                },
                "headroom history mode selected",
                mode="warn",
            )
        )
        relaxed_history = bool(allow_insufficient) and history_mode != "enforce"
        checks.append(
            _check_row(
                "capacity_headroom_history_reports_available",
                enough_history or relaxed_history,
                {
                    "available": available,
                    "required": min_required_runs,
                    "allow_insufficient_history": bool(allow_insufficient),
                    "relaxed_for_mode": bool(relaxed_history),
                },
                "enough recent load reports for headroom history",
                mode=history_mode,
            )
        )

        if window:
            latest_row = window[-1]
            history = window[:-1]
            latest_ratio = (_safe_float(latest_row.get("effective_rps"), 0.0) / target_peak_rps) if target_peak_rps > 0 else 0.0
            median_ratio = (
                _median([_safe_float(row.get("effective_rps"), 0.0) / target_peak_rps for row in history])
                if history and target_peak_rps > 0
                else latest_ratio
            )
            drop_ratio = max(0.0, (median_ratio - latest_ratio) / max(0.001, median_ratio))
            drop_ok = (drop_ratio <= max_latest_drop_ratio) or (not enough_history and relaxed_history)
            median_ok = (median_ratio >= required_headroom_ratio) or (not enough_history and relaxed_history)
            checks.append(
                _check_row(
                    "capacity_headroom_recent_drop_ratio",
                    drop_ok,
                    round(drop_ratio, 6),
                    f"<={max_latest_drop_ratio:.4f}",
                    mode=history_mode,
                )
            )
            checks.append(
                _check_row(
                    "capacity_headroom_recent_median_ratio",
                    median_ok,
                    round(median_ratio, 6),
                    f">={required_headroom_ratio:.4f}",
                    mode=history_mode,
                )
            )
            headroom_history = {
                "enabled": True,
                "mode": history_mode,
                "configured_mode": source_history_mode,
                "resolved_mode": configured_history_mode,
                "mode_override_source": override_source,
                "strict_promote_to_enforce": strict_promote,
                "promote_when_quick_with_sufficient_history": promote_when_quick_with_sufficient_history,
                "window": window,
                "latest_ratio": round(latest_ratio, 6),
                "median_ratio": round(median_ratio, 6),
                "latest_drop_ratio_to_window_median": round(drop_ratio, 6),
            }
    else:
        checks.append(
            _check_row(
                "capacity_headroom_history_disabled",
                True,
                False,
                "headroom history disabled",
                mode="warn",
            )
        )

    if bool(args.quick) and bool(targets.get("quick_allow_headroom_history_fallback", False)):
        headroom_row = next((row for row in checks if str(row.get("id")) == "capacity_headroom_ratio"), None)
        reports_row = next((row for row in checks if str(row.get("id")) == "capacity_headroom_history_reports_available"), None)
        drop_row = next((row for row in checks if str(row.get("id")) == "capacity_headroom_recent_drop_ratio"), None)
        median_row = next((row for row in checks if str(row.get("id")) == "capacity_headroom_recent_median_ratio"), None)
        headroom_ok = bool(headroom_row.get("ok")) if isinstance(headroom_row, dict) else False
        can_fallback = bool(
            isinstance(headroom_row, dict)
            and not headroom_ok
            and isinstance(reports_row, dict)
            and bool(reports_row.get("ok"))
            and isinstance(drop_row, dict)
            and bool(drop_row.get("ok"))
            and isinstance(median_row, dict)
            and bool(median_row.get("ok"))
            and str(drop_row.get("mode") or "warn") != "enforce"
            and str(median_row.get("mode") or "warn") != "enforce"
        )
        checks.append(
            _check_row(
                "capacity_headroom_history_fallback",
                can_fallback or headroom_ok,
                {
                    "applied": bool(can_fallback),
                    "headroom_mode_before": str(headroom_row.get("mode")) if isinstance(headroom_row, dict) else "",
                },
                "quick mode allows history-backed fallback",
                mode="warn",
            )
        )
        if can_fallback and isinstance(headroom_row, dict):
            headroom_row["mode"] = "warn"
            headroom_row["fallback"] = "headroom_history"

    soak_raw = _load_json(soak_path) if isinstance(soak_path, Path) else None
    soak_targets = _load_soak_targets(policy_raw, quick=bool(args.quick), citation_metrics=citation_metrics_node)
    soak_mode = "enforce" if bool(args.require_soak) else "warn"
    checks.append(
        _check_row(
            "capacity_soak_report_loaded",
            isinstance(soak_raw, dict),
            soak_path.as_posix() if isinstance(soak_path, Path) else "",
            "soak report exists and valid",
            mode=soak_mode,
        )
    )
    if isinstance(soak_raw, dict):
        aggregate = soak_raw.get("aggregate") if isinstance(soak_raw.get("aggregate"), dict) else {}
        soak_duration = _safe_float(soak_raw.get("duration_s"), 0.0)
        soak_windows = _safe_int(aggregate.get("window_count"), 0)
        soak_success = _safe_float(aggregate.get("success_rate"), 0.0)
        soak_p95 = _safe_float(aggregate.get("latency_p95_ms"), 0.0)
        soak_age_s = _report_age_s(report_path=soak_path, report_raw=soak_raw, now_ts=now_ts)
        checks.append(
            _check_row(
                "capacity_soak_report_fresh",
                soak_age_s <= float(targets.get("soak_report_max_age_s") or 0.0),
                round(soak_age_s, 3),
                f"<={float(targets.get('soak_report_max_age_s') or 0.0):.1f}s",
                mode=soak_mode,
            )
        )
        checks.append(
            _check_row(
                "capacity_soak_duration",
                soak_duration >= float(soak_targets.get("min_duration_s") or 0.0),
                round(soak_duration, 3),
                f">={float(soak_targets.get('min_duration_s') or 0.0):.1f}",
                mode=soak_mode,
            )
        )
        checks.append(
            _check_row(
                "capacity_soak_window_count",
                soak_windows >= int(float(soak_targets.get("min_window_count") or 0.0)),
                soak_windows,
                f">={int(float(soak_targets.get('min_window_count') or 0.0))}",
                mode=soak_mode,
            )
        )
        checks.append(
            _check_row(
                "capacity_soak_success_rate",
                soak_success >= float(soak_targets.get("min_success_rate") or 0.0),
                round(soak_success, 6),
                f">={float(soak_targets.get('min_success_rate') or 0.0):.4f}",
                mode=soak_mode,
            )
        )
        checks.append(
            _check_row(
                "capacity_soak_latency_p95_ms",
                soak_p95 <= float(soak_targets.get("max_latency_p95_ms") or 0.0),
                round(soak_p95, 3),
                f"<={float(soak_targets.get('max_latency_p95_ms') or 0.0):.2f}",
                mode=soak_mode,
            )
        )

    enforce_rows = [row for row in checks if str(row.get("mode") or "enforce") == "enforce"]
    ended = time.time()
    report = {
        "ok": all(bool(row.get("ok")) for row in enforce_rows),
        "started_at": round(started, 3),
        "ended_at": round(ended, 3),
        "duration_s": round(ended - started, 3),
        "quick": bool(args.quick),
        "strict": bool(args.strict),
        "require_soak": bool(args.require_soak),
        "paths": {
            "policy": policy_path.as_posix(),
            "load_report": load_path.as_posix() if isinstance(load_path, Path) else "",
            "load_pattern": str(args.load_pattern),
            "soak_report": soak_path.as_posix() if isinstance(soak_path, Path) else "",
        },
        "release_context": release_context,
        "capacity_profile": profile_info,
        "targets": {
            **targets,
            "headroom_history": headroom_history_targets,
            "soak": soak_targets,
        },
        "observed": {
            "effective_rps": round(effective_rps, 6),
            "headroom_ratio": round(headroom_ratio, 6),
            "headroom_history": headroom_history,
            "success_rate": round(success_rate, 6),
            "latency_p95_ms": round(p95, 3),
            "degraded_rate": round(degraded_rate, 6),
            "load_report_age_s": round(load_age_s, 3),
        },
        "checks": checks,
    }
    out_path = Path(str(args.out or Path(".data/out") / f"capacity_guard_{int(ended)}.json"))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if bool(report.get("ok")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
