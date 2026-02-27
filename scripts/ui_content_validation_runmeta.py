"""Ui Content Validation Runmeta command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple


def load_checkpoint(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"single_done": [], "multi_done": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            data.setdefault("single_done", [])
            data.setdefault("multi_done", [])
            return data
    except Exception:
        pass
    return {"single_done": [], "multi_done": []}


def save_checkpoint(path: Path, single_done: List[str], multi_done: List[str]) -> None:
    payload = {
        "updated_at": datetime.now().isoformat(),
        "single_done": single_done,
        "multi_done": multi_done,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def build_summary(run_data: Dict[str, Any]) -> Dict[str, Any]:
    single_results = run_data["results"]["single"]
    multi_results = run_data["results"]["multiround"]

    def _summary(items: List[Dict[str, Any]]) -> Dict[str, Any]:
        total = len(items)
        passed = sum(1 for x in items if x.get("passed"))
        failed = total - passed
        by_group_total = Counter(str(x.get("group", "")) for x in items)
        by_group_failed = Counter(str(x.get("group", "")) for x in items if not x.get("passed"))
        return {
            "total": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": round((passed / total) * 100, 2) if total else 0.0,
            "by_group_total": dict(by_group_total),
            "by_group_failed": dict(by_group_failed),
        }

    return {
        "single": _summary(single_results),
        "multiround": _summary(multi_results),
        "overall": _summary(single_results + multi_results),
    }


def write_summary_md(path: Path, run_data: Dict[str, Any], summary: Dict[str, Any]) -> None:
    lines: List[str] = []
    lines.append("# Content Validation Run Summary")
    lines.append("")
    lines.append(f"- Timestamp: `{run_data['timestamp']}`")
    lines.append(f"- Base URL: `{run_data['config']['base_url']}`")
    lines.append(f"- Group smoke: `{run_data['config']['group_smoke']}`")
    lines.append(f"- Run all: `{run_data['config']['run_all']}`")
    lines.append("")
    lines.append("## Scoreboard")
    lines.append("")
    lines.append("| Scope | Total | Passed | Failed | Pass Rate |")
    lines.append("|---|---:|---:|---:|---:|")
    for key, label in [("single", "Single"), ("multiround", "Multiround"), ("overall", "Overall")]:
        s = summary[key]
        lines.append(f"| {label} | {s['total']} | {s['passed']} | {s['failed']} | {s['pass_rate']}% |")
    lines.append("")

    failed_items: List[Tuple[str, str, str]] = []
    for row in run_data["results"]["single"]:
        if not row.get("passed"):
            failed_items.append((str(row.get("id")), str(row.get("group")), "; ".join(row.get("errors", [])[:4])))
    for row in run_data["results"]["multiround"]:
        if not row.get("passed"):
            failed_items.append((str(row.get("id")), str(row.get("group")), "; ".join(row.get("errors", [])[:4])))

    lines.append("## Failures")
    lines.append("")
    if not failed_items:
        lines.append("- No failures.")
    else:
        lines.append("| Case ID | Group | Error Preview |")
        lines.append("|---|---|---|")
        for case_id, group, err in failed_items:
            lines.append(f"| `{case_id}` | `{group}` | {err} |")
    lines.append("")

    lines.append("## Group Coverage")
    lines.append("")
    lines.append("- Single groups covered: " + str(len(summary["single"]["by_group_total"])))
    lines.append("- Multiround groups covered: " + str(len(summary["multiround"]["by_group_total"])))
    lines.append("")
    lines.append("## Artifacts")
    lines.append("")
    lines.append(f"- JSON: `{run_data['paths']['run_json']}`")
    lines.append(f"- Detail artifacts dir: `{run_data['paths']['artifacts_dir']}`")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args(default_dataset: str, default_multiset: str, default_out_root: str) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Playwright frontend content validation runner")
    p.add_argument("--dataset", default=default_dataset, help="single-round dataset JSON")
    p.add_argument("--multiround", default=default_multiset, help="multi-round dataset JSON")
    p.add_argument("--base-url", default="http://127.0.0.1:8000", help="web base url")
    p.add_argument("--start-server", action="store_true", help="start local server if base url is not reachable")
    p.add_argument("--disable-ollama", action="store_true", help="set WRITING_AGENT_USE_OLLAMA=0 when auto starting server")
    p.add_argument("--headed", action="store_true", help="run browser in headed mode")
    p.add_argument("--timeout-s", type=int, default=300, help="max wait for one generation cycle")
    p.add_argument("--poll-interval-s", type=float, default=0.6, help="state polling interval")
    p.add_argument("--group-smoke", action="store_true", help="run first case per group only")
    p.add_argument("--run-all", action="store_true", help="run all single + multiround cases")
    p.add_argument("--max-single", type=int, default=0, help="truncate single cases (0 = no cap)")
    p.add_argument("--max-multi", type=int, default=0, help="truncate multiround cases (0 = no cap)")
    p.add_argument("--single-start", type=int, default=1, help="single case start index, 1-based")
    p.add_argument("--single-end", type=int, default=99999, help="single case end index, 1-based")
    p.add_argument("--multi-start", type=int, default=1, help="multiround case start index, 1-based")
    p.add_argument("--multi-end", type=int, default=99999, help="multiround case end index, 1-based")
    p.add_argument("--single-ids", default="", help="comma-separated single case ids, e.g. C-001,C-022")
    p.add_argument("--multi-ids", default="", help="comma-separated multiround case ids, e.g. MR-001,MR-010")
    p.add_argument("--export-docx-all", action="store_true", help="export docx for every selected case")
    p.add_argument("--export-docx-for-format", action="store_true", help="export docx for format-required cases")
    p.add_argument("--checkpoint", default="", help="checkpoint file path")
    p.add_argument("--resume", action="store_true", help="resume from checkpoint (requires --checkpoint)")
    p.add_argument("--out-root", default=default_out_root, help="output root dir")
    return p.parse_args()


def load_and_select_cases(
    args: argparse.Namespace,
    *,
    read_json_fn,
    filter_by_index_fn,
    pick_first_per_group_fn,
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    dataset = read_json_fn(Path(args.dataset))
    multiset = read_json_fn(Path(args.multiround))
    single_cases = list(dataset.get("cases", []))
    multi_cases = list(multiset.get("cases", []))

    single_cases = filter_by_index_fn(single_cases, args.single_start, args.single_end)
    multi_cases = filter_by_index_fn(multi_cases, args.multi_start, args.multi_end)

    if args.group_smoke and not args.run_all:
        single_cases = pick_first_per_group_fn(single_cases)
        multi_cases = pick_first_per_group_fn(multi_cases)

    if args.max_single and args.max_single > 0:
        single_cases = single_cases[: args.max_single]
    if args.max_multi and args.max_multi > 0:
        multi_cases = multi_cases[: args.max_multi]

    single_ids = {x.strip() for x in str(args.single_ids or "").split(",") if x.strip()}
    multi_ids = {x.strip() for x in str(args.multi_ids or "").split(",") if x.strip()}
    if single_ids:
        single_cases = [c for c in single_cases if str(c.get("id", "")) in single_ids]
    if multi_ids:
        multi_cases = [c for c in multi_cases if str(c.get("id", "")) in multi_ids]

    return single_cases, multi_cases


def print_progress(prefix: str, idx: int, total: int, case_id: str, group: str) -> None:
    print(f"[{prefix}] {idx}/{total} {case_id} ({group})")
