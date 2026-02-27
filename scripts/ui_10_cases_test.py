# coding: utf-8
"""Ui 10 Cases Test command utility.

This script is part of the writing-agent operational toolchain.
"""

from pathlib import Path
from playwright.sync_api import sync_playwright
import os
import re
import time

BASE = "http://127.0.0.1:8000/"
OUT = Path(".data") / "out"
OUT.mkdir(parents=True, exist_ok=True)
LOG = OUT / "ui_10_cases_test.log"


def log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    prev = LOG.read_text(encoding="utf-8") if LOG.exists() else ""
    LOG.write_text(prev + f"[{ts}] {msg}\n", encoding="utf-8")


def answer_for(question: str, length_hint: str) -> str:
    q = question.strip()
    if "标题" in q and ("告诉我" in q or "标题吧" in q or "标题是" in q):
        return "工资管理系统"
    if "只需要包含" in q:
        return "是的"
    if ("目的" in q or "主要目的" in q) and "报告" in q:
        return "课程报告"
    if "格式" in q:
        return "默认"
    if "字体" in q or "样式" in q:
        return "标题黑体加粗，正文宋体小四"
    if "范围" in q or "包含哪些部分" in q:
        return "系统的设计和实现"
    if "字" in q or "页" in q:
        return length_hint or "3000字"
    return "默认"


def close_modal(page) -> None:
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
            page.wait_for_timeout(300)
        except Exception:
            pass


def upload_template(page, template_path: Path) -> None:
    page.click("#btnAttach")
    page.click("#btnUpload")
    page.set_input_files("#uploadFile", str(template_path.resolve()))
    log(f"file uploaded {template_path.name}")
    try:
        page.wait_for_selector("#modalRoot:not(.hidden)", timeout=180000)
        buttons = page.locator("#modalFoot button")
        if buttons.count() >= 3:
            buttons.nth(2).click(force=True)
        else:
            buttons.first.click(force=True)
        page.wait_for_timeout(300)
    except Exception:
        log("upload confirm modal not shown")
    close_modal(page)


def wait_generation_done(page, max_ticks: int = 300) -> bool:
    done = False
    for i in range(max_ticks):
        flow = page.evaluate("() => document.querySelector('#flowStatus')?.textContent || ''")
        status = page.evaluate("() => document.querySelector('#docStatus')?.textContent || ''")
        if i % 10 == 0:
            log(f"tick {i}: flow={flow} status={status}")
        if "完成" in flow:
            done = True
            break
        page.wait_for_timeout(3000)
    return done


cases = [
    {"title": "工资管理系统", "inst": "写一份工资管理系统课程报告，约3000字，默认格式。", "len": "3000字"},
    {"title": "库存管理系统", "inst": "生成库存管理系统课程设计报告，约3500字，默认格式。", "len": "3500字"},
    {"title": "选课系统", "inst": "写一份课程选课系统报告，约3000字，默认格式。", "len": "3000字"},
    {"title": "客户关系管理系统", "inst": "写一份CRM系统报告，约3000字，默认格式。", "len": "3000字"},
    {"title": "设备维修管理系统", "inst": "生成设备维修管理系统报告，约3200字，默认格式。", "len": "3200字"},
    {"title": "图书管理系统", "inst": "写一份图书管理系统报告，约2800字，默认格式。", "len": "2800字"},
    {"title": "进销存系统", "inst": "生成进销存系统课程报告，约3500字，默认格式。", "len": "3500字"},
    {"title": "模板-专业项目设计", "inst": "写一份工资管理系统报告，约3000字，默认格式。", "len": "3000字", "tpl": "专业项目设计(1).docx"},
    {"title": "模板-章节结构", "inst": "写一份工资管理系统报告，约3000字，默认格式。", "len": "3000字", "tpl": "一种可选的章节结构（仅供参考）.docx"},
    {"title": "模板-开题报告", "inst": "写一份工资管理系统报告，约3000字，默认格式。", "len": "3000字", "tpl": "附件4：广东工业大学本科生毕业设计（论文）开题报告.docx"},
]

start_idx = int(os.environ.get("UI_CASE_START", "1"))
end_idx = int(os.environ.get("UI_CASE_END", str(len(cases))))
start_idx = max(1, start_idx)
end_idx = min(len(cases), end_idx)


with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    for idx, case in enumerate(cases, 1):
        if idx < start_idx or idx > end_idx:
            continue
        page.goto(BASE, wait_until="domcontentloaded")
        page.wait_for_selector("#instruction")
        log(f"case {idx}: {case['title']}")

        if case.get("tpl"):
            upload_template(page, Path("templates") / case["tpl"])

        page.fill("#instruction", case["inst"])
        close_modal(page)
        close_modal(page)
        page.click("#btnGenerate")

        # answer interviews
        for _ in range(24):
            try:
                page.wait_for_function(
                    "() => document.querySelector('#btnGenerate')?.dataset.mode === 'reply'",
                    timeout=20000,
                )
            except Exception:
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
            answer = answer_for(question, case["len"])
            page.fill("#instruction", answer)
            close_modal(page)
            page.click("#btnGenerate")
            log(f"answered {answer}")

        done = wait_generation_done(page, max_ticks=260)
        if not done:
            log("generation not completed; continue")

        # ask format question
        page.fill("#instruction", "给我讲讲文档的格式")
        close_modal(page)
        page.click("#btnGenerate")
        page.wait_for_timeout(800)

        # apply formatting/outline command
        page.fill("#instruction", "增大标题字号和正文字号，增加“需求分析”作为一章")
        close_modal(page)
        page.click("#btnGenerate")
        page.wait_for_timeout(1200)

        # insert a figure if missing and test edit
        try:
            page.click('.tab[data-tab="edit"]')
            page.click("#tbFigure")
            page.wait_for_timeout(500)
            fig = page.locator("#editor figure.fig").first
            box = fig.bounding_box()
            if box:
                page.mouse.dblclick(box["x"] + 10, box["y"] + 10)
                page.wait_for_selector("#modalRoot:not(.hidden)", timeout=10000)
                area = page.locator("#modalRoot textarea").first
                if area.count() > 0:
                    area.fill('{"type":"bar","caption":"样例图表","data":{"labels":["A","B","C"],"values":[10,20,15]}}')
                page.locator("#modalRoot button", has_text="更新图表").click(force=True)
        except Exception:
            log("figure edit skipped")
        close_modal(page)

        stamp = time.strftime("%Y%m%d_%H%M%S")
        safe = re.sub(r"[\\\\/:*?\"<>|]+", "", case["title"])[:24] or "case"
        out_path = OUT / f"ui_case_{idx:02d}_{safe}_{stamp}.docx"
        close_modal(page)
        with page.expect_download() as download_info:
            page.click("#btnDownload")
        download = download_info.value
        download.save_as(str(out_path.resolve()))
        log(f"saved {out_path.name}")

    browser.close()
