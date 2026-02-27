#!/usr/bin/env python
"""Bench Thresholds command utility.

This script is part of the writing-agent operational toolchain.
"""

import json
import os
from pathlib import Path

CURRENT_DIR = Path(os.environ.get("CURRENT_DIR", "target/criterion"))
THRESHOLDS = {
    "typing_latency": 8.0e6,
    "render_frame_sim": 8.33e6,
    "scroll_10k_lines": 8.33e6,
    "undo_100_ops": 50.0e6,
    "layout_1000_chars": 3.0e6,
    "shape_1000_chars": 2.0e6,
    "layout_blocks": 5.0e6,
    "layout_blocks_cached": 0.5e6,
    "render_visible_sim": 8.33e6,
    "layout_10k_lines_block": 8.0e6,
    "measure_10k_words": 5.0e6,
}

def load_estimates(path: Path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("mean", {}).get("point_estimate")
    except Exception:
        return None

def main():
    if not CURRENT_DIR.exists():
        print(f"[perf] current dir not found: {CURRENT_DIR}")
        return 1
    failed = False
    for new_est in CURRENT_DIR.rglob("new/estimates.json"):
        rel = new_est.relative_to(CURRENT_DIR)
        bench_name = rel.parts[-3] if len(rel.parts) >= 3 else ""
        if bench_name not in THRESHOLDS:
            continue
        mean = load_estimates(new_est)
        if mean is None:
            continue
        if mean > THRESHOLDS[bench_name]:
            failed = True
            print(f"[perf] threshold fail {bench_name}: {mean:.2f} > {THRESHOLDS[bench_name]:.2f}")
    if failed:
        return 2
    print("[perf] thresholds ok")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
