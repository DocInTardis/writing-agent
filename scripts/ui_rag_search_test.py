# coding: utf-8
"""Ui Rag Search Test command utility.

This script is part of the writing-agent operational toolchain.
"""

from pathlib import Path
from playwright.sync_api import sync_playwright
import requests
from docx import Document
import time

BASE = "http://127.0.0.1:8000/"
OUT = Path(".data") / "out"
OUT.mkdir(parents=True, exist_ok=True)
LOG = OUT / "ui_rag_search_test.log"


def log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    prev = LOG.read_text(encoding="utf-8") if LOG.exists() else ""
    LOG.write_text(prev + f"[{ts}] {msg}\n", encoding="utf-8")


def close_modal(page) -> None:
    for _ in range(5):
        try:
            if not page.is_visible("#modalRoot:not(.hidden)"):
                return
        except Exception:
            return
        try:
            btns = page.locator("#modalFoot button")
            if btns.count() > 0:
                btns.first.click(force=True)
            else:
                page.click("#modalRoot [data-close='1']", force=True)
        except Exception:
            pass
        page.wait_for_timeout(200)


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        page.set_default_timeout(30000)
        page.set_default_navigation_timeout(60000)
        page.goto(BASE, wait_until="domcontentloaded")
        page.wait_for_function("() => window.__wa_ready === true", timeout=60000)
        page.wait_for_selector("#instruction")
        close_modal(page)
        doc_id = page.eval_on_selector(".app", "el => el.getAttribute('data-doc-id') || ''").strip()
        if doc_id:
            log(f"doc_id={doc_id}")

        # open attach menu -> online search
        page.click("#btnAttach")
        page.click("#btnRagSearch")
        page.wait_for_selector("#modalRoot:not(.hidden)")
        page.fill("#modalRoot input.input", "工资管理 系统设计")
        page.click("#modalRoot button.btn.primary")
        page.wait_for_timeout(2000)

        # select first 3 results
        checkboxes = page.locator("#modalRoot input[type=checkbox]")
        cnt = checkboxes.count()
        for i in range(min(3, cnt)):
            checkboxes.nth(i).click(force=True)
        # click ingest
        btns = page.locator("#modalFoot button")
        if btns.count() >= 2:
            btns.last.click(force=True)
        page.wait_for_timeout(5000)
        close_modal(page)

        # generate
        instruction = "用默认格式写一份工资管理系统课程设计报告，约2000字，没有模板，包含需求分析、总体设计、数据库设计、测试与结果。"
        page.fill("#instruction", instruction)
        page.click("#btnGenerate")
        # answer pending questions
        for _ in range(8):
            try:
                page.wait_for_function("() => document.querySelector('#btnGenerate')?.dataset.mode === 'reply'", timeout=8000)
            except Exception:
                break
            last = page.evaluate("""
() => {
  const rows = Array.from(document.querySelectorAll('#chatHistory .chat-msg.system'));
  const last = rows[rows.length - 1];
  return last ? last.innerText : '';
}
""")
            if "长度" in last or "字数" in last:
                page.fill("#instruction", "2000字")
            elif "目的" in last or "用途" in last:
                page.fill("#instruction", "课程设计")
            elif "格式" in last or "模板" in last:
                page.fill("#instruction", "默认")
            else:
                page.fill("#instruction", "系统设计与实现")
            page.click("#btnGenerate")
            page.wait_for_timeout(200)

        page.wait_for_function("() => (document.querySelector('#docStatus')?.innerText || '').includes('完成')", timeout=120000)
        log("generation done")
        if doc_id:
            try:
                data = requests.get(f"{BASE}api/doc/{doc_id}", timeout=10).json()
                text = str(data.get("text") or "")
                head = text[:200].replace("\n", " ")
                log(f"doc_text_len={len(text)} head={head}")
            except Exception as e:
                log(f"doc_text_fetch_failed {e}")

        # export (capture download)
        with page.expect_download() as dl_info:
            page.click("#btnDownload")
        download = dl_info.value
        fname = f"ui_rag_search_{int(time.time())}.docx"
        out_path = OUT / fname
        download.save_as(out_path)
        log(f"export saved {out_path.name}")

        # verify references and citations
        doc = Document(str(out_path))
        text = "\n".join([para.text for para in doc.paragraphs])
        has_refs = "参考文献" in text
        has_cite = "[1]" in text
        log(f"doc check refs={has_refs} cite={has_cite}")
        browser.close()


if __name__ == "__main__":
    run()
