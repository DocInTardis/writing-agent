#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Strict UI automation (Playwright):
- Validate left-side thought chain updates
- Validate right-side editor shows incremental "typing" growth
- Save screenshots + debug artifacts
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


BASE_URL = os.environ.get("WA_BASE_URL", "http://127.0.0.1:8000")
OUT_DIR = Path(os.environ.get("WA_UI_ARTIFACTS", "artifacts/ui_playwright")).resolve()
OUT_DIR.mkdir(parents=True, exist_ok=True)
TYPING_MIN_INCREMENTS = int(os.environ.get("WA_TYPING_MIN_INCREMENTS", "2"))
TYPING_MIN_CHARS = int(os.environ.get("WA_TYPING_MIN_CHARS", "30"))
TYPING_TIMEOUT_MS = int(os.environ.get("WA_TYPING_TIMEOUT_MS", "240000"))


def main() -> int:
    instruction = (
        "写一份关于人工智能在教育中的应用的简短报告，"
        "包含背景、现状、应用、挑战、展望五节，约150字，学术风格。"
    )

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="zh-CN",
        )
        page = context.new_page()
        console_logs: list[dict] = []
        page_errors: list[dict] = []

        def _log_console(msg) -> None:
            console_logs.append({"type": msg.type, "text": msg.text})

        def _log_error(err) -> None:
            page_errors.append({"message": str(err)})

        page.on("console", _log_console)
        page.on("pageerror", _log_error)

        page.goto(BASE_URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_selector(".composer textarea", timeout=30000)
        page.wait_for_selector(".editable", timeout=30000)

        # Install typing observer before generation.
        page.evaluate(
            """
            (() => {
              if (window.__waTypingObserver) return;
              const el = document.querySelector('.editable');
              if (!el) return;
              window.__waTypingEvents = [];
              const record = () => {
                const len = (el.innerText || '').length;
                window.__waTypingEvents.push({ t: Date.now(), len });
              };
              const obs = new MutationObserver(() => record());
              obs.observe(el, { childList: true, subtree: true, characterData: true });
              window.__waTypingObserver = obs;
              record();
            })();
            """
        )

        # Send instruction to start generation.
        page.fill(".composer textarea", instruction)
        page.click(".composer button")

        # Wait for thought items to appear.
        try:
            page.wait_for_function(
                "document.querySelectorAll('.thought-item').length > 0",
                timeout=90000,
            )
        except PlaywrightTimeoutError:
            page.screenshot(path=str(OUT_DIR / "timeout_thoughts.png"), full_page=True)
            raise

        page.screenshot(path=str(OUT_DIR / "thoughts.png"), full_page=True)

        # Wait for incremental typing: at least N increases and enough chars.
        try:
            page.wait_for_function(
                """
                (() => {
                  const ev = window.__waTypingEvents || [];
                  if (ev.length < 3) return false;
                  let inc = 0;
                  for (let i = 1; i < ev.length; i++) {
                    if (ev[i].len > ev[i - 1].len) inc += 1;
                  }
                  const first = ev[0];
                  const last = ev[ev.length - 1];
                  return inc >= %d && (last.len - first.len) >= %d;
                })()
                """ % (TYPING_MIN_INCREMENTS, TYPING_MIN_CHARS),
                timeout=TYPING_TIMEOUT_MS,
            )
        except PlaywrightTimeoutError:
            page.screenshot(path=str(OUT_DIR / "timeout_typing.png"), full_page=True)
            events = page.evaluate("window.__waTypingEvents || []")
            (OUT_DIR / "typing_events_timeout.json").write_text(
                json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            try:
                state = page.evaluate(
                    """(() => {
                      const editable = document.querySelector('.editable');
                      const doc = document.querySelector('.status .doc');
                      const flow = document.querySelector('.status .flow');
                      const count = document.querySelector('.status .count');
                      let storeTextLen = null;
                      let storeTextPreview = '';
                      try {
                        const v = window.__waGetStore ? window.__waGetStore('sourceText') : undefined;
                        storeTextLen = v ? v.length : 0;
                        storeTextPreview = v ? v.slice(0, 200) : '';
                      } catch {}
                      return {
                        editableTextLen: editable ? (editable.textContent || '').length : 0,
                        editableHtmlLen: editable ? (editable.innerHTML || '').length : 0,
                        docStatus: doc ? doc.textContent : '',
                        flowStatus: flow ? flow.textContent : '',
                        wordCount: count ? count.textContent : '',
                        storeTextLen,
                        storeTextPreview
                      };
                    })()"""
                )
            except Exception:
                state = {}
            (OUT_DIR / "ui_state_timeout.json").write_text(
                json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            if console_logs:
                (OUT_DIR / "console_logs.json").write_text(
                    json.dumps(console_logs, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            if page_errors:
                (OUT_DIR / "page_errors.json").write_text(
                    json.dumps(page_errors, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            raise

        page.screenshot(path=str(OUT_DIR / "typing.png"), full_page=True)

        events = page.evaluate("window.__waTypingEvents || []")
        (OUT_DIR / "typing_events.json").write_text(
            json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        if console_logs:
            (OUT_DIR / "console_logs.json").write_text(
                json.dumps(console_logs, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        if page_errors:
            (OUT_DIR / "page_errors.json").write_text(
                json.dumps(page_errors, ensure_ascii=False, indent=2), encoding="utf-8"
            )

        # Extra snapshot after a short delay.
        time.sleep(2)
        page.screenshot(path=str(OUT_DIR / "typing_more.png"), full_page=True)

        context.close()
        browser.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
