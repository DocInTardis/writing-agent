"""Ui Timeout Probe command utility.

This script is part of the writing-agent operational toolchain.
"""

from __future__ import annotations

import os
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

BASE_URL = os.environ.get("WA_BASE_URL", "http://127.0.0.1:8000")
PROMPTS = [
    "生成一个不限内容的周报",
    "写一份项目周报：背景、进度、问题、下周计划，1000字左右",
    "请生成一份调研报告：主题为数据中台，含背景/现状/问题/建议/参考文献",
    "写一份产品复盘报告，包含目标、过程、数据、结论、后续计划",
    "生成一份部门工作总结，强调风险与跨部门协作",
]
PROMPT_COUNT = int(os.environ.get("WA_PROMPT_COUNT", "5"))


def _is_done(doc: str) -> bool:
    s = (doc or '').strip()
    return s == '\u5b8c\u6210' or '\u5df2\u5b8c\u6210' in s or '\u5b8c\u6210\u751f\u6210' in s




@dataclass
class RunResult:
    prompt: str
    status: str
    total_ms: int
    first_event_ms: int
    max_gap_ms: int
    events: list[dict[str, Any]]


def _collect_events(page) -> None:
    page.evaluate(
        """
        () => {
          window.__waEvents = []
          const push = (label) => window.__waEvents.push({ t: performance.now(), label })
          const doc = document.querySelector('.status .doc')
          const thoughts = document.querySelector('.thought-list')
          let lastDoc = doc ? doc.textContent : ''
          let lastCount = thoughts ? thoughts.childElementCount : 0
          if (doc) {
            new MutationObserver(() => {
              const txt = doc.textContent || ''
              if (txt !== lastDoc) {
                lastDoc = txt
                push('doc:' + txt)
              }
            }).observe(doc, { childList: true, characterData: true, subtree: true })
          }
          if (thoughts) {
            new MutationObserver(() => {
              const c = thoughts.childElementCount || 0
              if (c !== lastCount) {
                lastCount = c
                push('thought:' + c)
              }
            }).observe(thoughts, { childList: true, subtree: true })
          }
          push('start')
        }
        """
    )


def _read_events(page) -> list[dict[str, Any]]:
    return page.evaluate("() => window.__waEvents || []")


def _compute_max_gap(events: list[dict[str, Any]]) -> int:
    if len(events) < 2:
        return 0
    events = sorted(events, key=lambda x: x.get("t", 0))
    gaps = [max(0, int(events[i]["t"] - events[i - 1]["t"])) for i in range(1, len(events))]
    return max(gaps) if gaps else 0


def run_once(page, prompt: str, timeout_ms: int = 900000) -> RunResult:
    page.goto(BASE_URL, wait_until="domcontentloaded", timeout=120000)
    page.wait_for_selector(".composer textarea", timeout=15000)
    _collect_events(page)
    page.fill(".composer textarea", prompt)
    page.click(".composer button")

    start = time.time()
    status = "running"
    first_event_ms = 0
    last_doc = ""

    while True:
        now = time.time()
        if (now - start) * 1000 > timeout_ms:
            status = "timeout"
            break
        doc = page.text_content(".status .doc") or ""
        if doc != last_doc and not first_event_ms:
            first_event_ms = int((now - start) * 1000)
        last_doc = doc
        if _is_done(doc):
            status = "done"
            break
        if "失败" in doc or "已中止" in doc:
            status = doc
            break
        time.sleep(0.5)

    events = _read_events(page)
    total_ms = int((time.time() - start) * 1000)
    if not first_event_ms and events:
        first_event_ms = int(events[0].get("t", 0))
    max_gap_ms = _compute_max_gap(events)
    return RunResult(
        prompt=prompt,
        status=status,
        total_ms=total_ms,
        first_event_ms=first_event_ms,
        max_gap_ms=max_gap_ms,
        events=events,
    )


def main() -> None:
    results: list[RunResult] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for prompt in PROMPTS[: max(1, PROMPT_COUNT)]:
            try:
                page = browser.new_page()
                res = run_once(page, prompt)
                results.append(res)
                page.close()
            except PlaywrightTimeoutError as e:
                results.append(
                    RunResult(
                        prompt=prompt,
                        status=f"playwright timeout: {e}",
                        total_ms=0,
                        first_event_ms=0,
                        max_gap_ms=0,
                        events=[],
                    )
                )
        browser.close()

    out = {
        "base_url": BASE_URL,
        "results": [r.__dict__ for r in results],
        "max_gap_ms": max([r.max_gap_ms for r in results] + [0]),
        "max_total_ms": max([r.total_ms for r in results] + [0]),
    }
    report_path = Path(".data/out/ui_timeout_probe.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
