# coding: utf-8
"""Ui Flow Test command utility.

This script is part of the writing-agent operational toolchain.
"""

from pathlib import Path
from playwright.sync_api import sync_playwright
import os
import re
import time

base = "http://127.0.0.1:8000/"
log_path = Path(".data") / "out" / "ui_flow_test.log"
log_path.parent.mkdir(parents=True, exist_ok=True)


def log(msg):
    ts = time.strftime("%H:%M:%S")
    existing = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    log_path.write_text(existing + f"[{ts}] {msg}\n", encoding="utf-8")


def extract_instruction_placeholder():
    html = Path("writing_agent/web/templates/v2_workbench2.html").read_text(encoding="utf-8")
    m = re.search(r'id="instruction"[^>]*placeholder="([^"]+)"', html)
    return m.group(1) if m else ""


def extract_title(sample):
    if not sample:
        return ""
    m = re.search(r"\u300a(.+?)\u300b", sample)
    return m.group(1) if m else ""


def extract_length_hint(sample):
    if not sample:
        return ""
    m = re.search(r"(\d+\u5b57)", sample)
    if m:
        return m.group(1)
    m = re.search(r"(\d+\u9875)", sample)
    return m.group(1) if m else ""


def answer_for(question, length_hint):
    q = question.strip()
    if "标题" in q and ("告诉我" in q or "标题吧" in q or "标题是" in q):
        return "工资管理系统"
    if "只需要包含" in q:
        return "是的"
    if ("目的" in q or "主要目的" in q) and "报告" in q:
        return "课程报告"
    if "格式" in q:
        return "使用默认的吧"
    if "字体" in q or "样式" in q:
        return "标题黑体加粗，正文宋体小四"
    if "范围" in q or "包含哪些部分" in q:
        return "系统的设计和实现"
    if "标题" in q and ("先告诉我" in q or "标题吧" in q or "标题是" in q):
        return "工资管理系统"
    m = re.search(r"\u201C(.+?)\u201D", q)
    if m:
        return m.group(1)
    if "\u5b57" in q or "\u9875" in q:
        return length_hint or "8000"
    if "/" in q:
        seg = q
        if "\uFF1A" in q:
            seg = q.split("\uFF1A", 1)[1]
        elif ":" in q:
            seg = q.split(":", 1)[1]
        seg = re.sub(r"[\u3002\uFF1F?]", "", seg)
        opts = [o.strip() for o in seg.split("/") if o.strip()]
        if any("\u8bbe\u8ba1" in o for o in opts) or any("\u5b9e\u73b0" in o for o in opts):
            chosen = [o for o in opts if "\u8bbe\u8ba1" in o or "\u5b9e\u73b0" in o]
            if chosen:
                return "/".join(chosen)
        if opts:
            return opts[0]
    return length_hint or ""


def close_modal(page):
    for _ in range(5):
        try:
            if not page.is_visible("#modalRoot:not(.hidden)"):
                return
        except Exception:
            return
        try:
            buttons = page.locator("#modalFoot button")
            if buttons.count() > 0:
                buttons.first.click(force=True)
            else:
                page.click("#modalRoot [data-close='1']", force=True)
        except Exception:
            pass
        try:
            page.wait_for_timeout(400)
        except Exception:
            pass


def pick_template():
    root_converted = list(Path(".").glob("*_converted.docx"))
    if root_converted:
        return max(root_converted, key=lambda p: p.stat().st_size)
    root_docx = list(Path(".").glob("*.docx"))
    if root_docx:
        return max(root_docx, key=lambda p: p.stat().st_size)
    docx_files = sorted(Path("templates").glob("*.docx"), key=lambda p: p.stat().st_size, reverse=True)
    if not docx_files:
        raise SystemExit("No template .docx found")
    return docx_files[0]


sample = extract_instruction_placeholder()
length_hint = os.environ.get("UI_FLOW_LENGTH", "").strip() or (extract_length_hint(sample) or "3000字")
raw_cases = os.environ.get("UI_FLOW_CASES", "").strip()
if raw_cases:
    instructions = [s.strip() for s in raw_cases.split("|") if s.strip()]
else:
    instructions = ["写一份工资管理系统的报告"]
log(f"instruction count={len(instructions)}")


def safe_name(text: str) -> str:
    base = extract_title(text) or text
    base = re.sub(r"[\\s\\t\\r\\n]+", "", base)
    base = re.sub(r"[\\\\/:*?\"<>|]+", "", base)
    return base[:24] or "sample"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    def on_request(req):
        url = req.url
        if "/api/doc/" in url:
            log(f"request {req.method} {url}")

    def on_response(resp):
        url = resp.url
        if "/api/doc/" in url:
            log(f"response {resp.status} {url}")

    def on_fail(req):
        url = req.url
        if "/api/doc/" in url:
            log(f"request failed {url} {req.failure}")

    page.on("request", on_request)
    page.on("response", on_response)
    page.on("requestfailed", on_fail)

    def answer_pending_reply():
        try:
            is_reply = page.evaluate(
                "() => { const btn = document.querySelector('#btnGenerate'); return btn && !btn.disabled && btn.dataset.mode === 'reply'; }"
            )
        except Exception:
            return False
        if not is_reply:
            return False
        question = page.evaluate(
            """
() => {
  const rows = Array.from(document.querySelectorAll('#chatHistory .chat-msg.system'));
  const last = rows[rows.length - 1];
  return last ? last.innerText : '';
}
"""
        )
        if not question:
            return False
        answer = answer_for(question, length_hint) or length_hint or "8000"
        page.fill("#instruction", answer)
        close_modal(page)
        page.click("#btnGenerate")
        log(f"answered {answer}")
        close_modal(page)
        return True

    for idx, instruction in enumerate(instructions, 1):
        page.goto(base, wait_until="domcontentloaded")
        page.wait_for_selector("#instruction")
        log("page loaded")

        skip_upload = os.environ.get("UI_FLOW_SKIP_UPLOAD", "").strip().lower() in {"1", "true", "yes", "on"}
        if not skip_upload:
            template_path = pick_template()
            page.click("#btnAttach")
            page.click("#btnUpload")
            page.set_input_files("#uploadFile", str(template_path.resolve()))
            log(f"file uploaded {template_path.name}")

            try:
                page.wait_for_selector("#modalRoot:not(.hidden)", timeout=120000)
                buttons = page.locator("#modalFoot button")
                if buttons.count() >= 3:
                    buttons.nth(2).click(force=True)
                else:
                    buttons.first.click(force=True)
                page.wait_for_timeout(500)
                close_modal(page)
            except Exception:
                log("upload confirm modal not shown")
                close_modal(page)
        else:
            log("skip upload")

        page.wait_for_function("() => !document.querySelector('#instruction').disabled", timeout=300000)
        close_modal(page)

        page.fill("#instruction", instruction or "test")
        close_modal(page)
        page.click("#btnGenerate")
        log(f"sent instruction {idx}")

        for _ in range(20):
            try:
                page.wait_for_function("() => document.querySelector('#btnGenerate')?.dataset.mode === 'reply'", timeout=20000)
            except Exception:
                log("no pending reply, break")
                break
            question = page.evaluate(
                """
() => {
  const rows = Array.from(document.querySelectorAll('#chatHistory .chat-msg.system'));
  const last = rows[rows.length - 1];
  return last ? last.innerText : '';
}
"""
            )
            log(f"question {question}")
            answer = answer_for(question, length_hint) or length_hint or "8000"
            page.fill("#instruction", answer)
            close_modal(page)
            page.click("#btnGenerate")
            log(f"answered {answer}")
            close_modal(page)

        answer_pending_reply()

        flow = page.evaluate("() => document.querySelector('#flowStatus')?.textContent || ''")
        log(f"flow status {flow}")
        # Avoid double-submit; allow the first request to proceed.

        done = False
        for i in range(300):
            if answer_pending_reply():
                page.wait_for_timeout(800)
            flow = page.evaluate("() => document.querySelector('#flowStatus')?.textContent || ''")
            status = page.evaluate("() => document.querySelector('#docStatus')?.textContent || ''")
            log(f"tick {i}: flow={flow} status={status}")
            if "\u5b8c\u6210" in flow:
                done = True
                break
            page.wait_for_timeout(3000)

        if not done:
            log("generation not completed; stopping")
            browser.close()
            raise SystemExit(1)

        # Select some text and ensure buttons still respond.
        try:
            page.click('.tab[data-tab="edit"]')
        except Exception:
            pass
        page.evaluate(
            """
() => {
  const editor = document.querySelector('#editor');
  if (!editor) return false;
  const target = editor.querySelector('p, div');
  if (!target) return false;
  const range = document.createRange();
  range.selectNodeContents(target);
  const sel = window.getSelection();
  sel.removeAllRanges();
  sel.addRange(range);
  return true;
}
"""
        )
        try:
            page.wait_for_selector(".selection-menu:not(.hidden)", timeout=5000)
            page.click(".selection-menu button", force=True)
            log("selection menu click ok")
        except Exception:
            log("selection menu not clickable")

        close_modal(page)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        name = safe_name(instruction)
        out_path = Path(".data") / "out" / f"ui_sample_{name}_{stamp}.docx"
        with page.expect_download() as download_info:
            page.click("#btnDownload")
        download = download_info.value
        download.save_as(str(out_path.resolve()))
        log(f"saved {out_path}")

    browser.close()
