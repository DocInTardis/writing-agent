#!/usr/bin/env python
"""Compare Bench command utility.

This script is part of the writing-agent operational toolchain.
"""

import json
import os
from pathlib import Path

BASELINE_DIR = Path(os.environ.get("BASELINE_DIR", "perf_baseline"))
CURRENT_DIR = Path(os.environ.get("CURRENT_DIR", "target/criterion"))
THRESHOLD = float(os.environ.get("PERF_THRESHOLD", "0.05"))
THRESHOLDS = {
    "typing_latency": 8.0e6,          # 8ms in ns (criterion uses ns for very small benches; keep large threshold)
    "render_frame_sim": 8.33e6,       # 8.33ms in ns
    "scroll_10k_lines": 8.33e6,       # 120fps budget
    "undo_100_ops": 50.0e6,           # 50ms in ns
    "layout_1000_chars": 3.0e6,       # 3ms in ns
    "shape_1000_chars": 2.0e6,        # 2ms in ns
}

def load_estimates(path: Path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("mean", {}).get("point_estimate")
    except Exception:
        return None

def main():
    if not BASELINE_DIR.exists():
        print(f"[perf] baseline dir not found: {BASELINE_DIR} (skip)")
        return 0
    if not CURRENT_DIR.exists():
        print(f"[perf] current dir not found: {CURRENT_DIR}")
        return 1
    failed = False
    threshold_failed = False
    for new_est in CURRENT_DIR.rglob("new/estimates.json"):
        rel = new_est.relative_to(CURRENT_DIR)
        base_est = BASELINE_DIR / rel
        bench_name = rel.parts[-3] if len(rel.parts) >= 3 else ""
        if not base_est.exists():
            # even without baseline, enforce absolute thresholds if configured
            new_mean = load_estimates(new_est)
            if new_mean is not None and bench_name in THRESHOLDS:
                if new_mean > THRESHOLDS[bench_name]:
                    threshold_failed = True
                    print(f"[perf] threshold fail {bench_name}: {new_mean:.2f} > {THRESHOLDS[bench_name]:.2f}")
            continue
        new_mean = load_estimates(new_est)
        base_mean = load_estimates(base_est)
        if new_mean is None or base_mean is None:
            continue
        if bench_name in THRESHOLDS and new_mean > THRESHOLDS[bench_name]:
            threshold_failed = True
            print(f"[perf] threshold fail {bench_name}: {new_mean:.2f} > {THRESHOLDS[bench_name]:.2f}")
        if base_mean == 0:
            continue
        change = (new_mean - base_mean) / base_mean
        if change > THRESHOLD:
            failed = True
            print(f"[perf] regression {change*100:.2f}%: {rel.parent.parent}")
    if failed or threshold_failed:
        print(f"[perf] failed: regression > {THRESHOLD*100:.1f}%")
        return 2
    print("[perf] ok")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
