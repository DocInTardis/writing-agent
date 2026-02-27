# coding: utf-8
"""Ui 10 Rounds Wysiwyg command utility.

This script is part of the writing-agent operational toolchain.
"""

from pathlib import Path
from playwright.sync_api import sync_playwright
import time
import re

BASE = "http://127.0.0.1:8000/"
OUT = Path(".data") / "out"
OUT.mkdir(parents=True, exist_ok=True)
LOG = OUT / "ui_10_rounds_wysiwyg.log"

SEND_BTN = "\u53d1\u9001"
SAVE_BTN = "\u4fdd\u5b58"
EXPORT_BTN = "\u5bfc\u51fa Word"
REQ_SECTIONS = ("\u80cc\u666f", "\u672c\u5468\u5de5\u4f5c", "\u4e0b\u5468\u8ba1\u5212")


def log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    prev = LOG.read_text(encoding="utf-8") if LOG.exists() else ""
    LOG.write_text(prev + f"[{ts}] {msg}\n", encoding="utf-8")


def click_button(page, label: str) -> None:
    page.locator("button", has_text=label).first.click()


def get_doc_id(page) -> str:
    try:
        return page.evaluate(
            "() => document.body?.dataset?.docId || window.__DOC_ID__ || ''"
        )
    except Exception:
        return ""


def fetch_doc_text(page, doc_id: str) -> str:
    try:
        resp = page.request.get(f"{BASE}api/doc/{doc_id}")
        if not resp.ok:
            return ""
        data = resp.json()
        return str(data.get("text") or "")
    except Exception:
        return ""


def wait_doc_text(page, timeout_s: int = 240) -> str:
    end = time.time() + timeout_s
    text = ""
    doc_id = ""
    last_log = 0.0
    while time.time() < end:
        if not doc_id:
            doc_id = get_doc_id(page)
        if doc_id:
            text = fetch_doc_text(page, doc_id)
        flow = ""
        doc = ""
        try:
            flow = page.locator(".status .flow").inner_text().strip()
            doc = page.locator(".status .doc").inner_text().strip()
        except Exception:
            flow = ""
            doc = ""
        now = time.time()
        if now - last_log > 5:
            log(f"wait flow={flow} doc={doc} text_len={len(text)}")
            last_log = now
        if "失败" in flow or "失败" in doc:
            return text
        if all(k in text for k in REQ_SECTIONS) and len(text) > 120:
            return text
        if flow.strip() in {"完成", "DONE"}:
            return text
        page.wait_for_timeout(1000)
    return text


cases = [
    ("电商运营", "生成一份周报，包含背景、本周工作、下周计划，300字左右。背景是电商运营团队，本周做了促销复盘与品类优化。"),
    ("产品研发", "生成一份周报，包含背景、本周工作、下周计划，300字左右。背景是产品研发团队，本周完成了核心模块联调。"),
    ("市场投放", "生成一份周报，包含背景、本周工作、下周计划，300字左右。背景是市场投放，本周完成A/B广告测试与素材迭代。"),
    ("客户成功", "生成一份周报，包含背景、本周工作、下周计划，300字左右。背景是客户成功团队，本周推进续费与回访。"),
    ("数据分析", "生成一份周报，包含背景、本周工作、下周计划，300字左右。背景是数据分析，本周完成指标口径梳理与看板优化。"),
    ("供应链", "生成一份周报，包含背景、本周工作、下周计划，300字左右。背景是供应链，本周完成库存盘点与备货策略调整。"),
    ("客服中心", "生成一份周报，包含背景、本周工作、下周计划，300字左右。背景是客服中心，本周优化工单分类与响应SLA。"),
    ("内容运营", "生成一份周报，包含背景、本周工作、下周计划，300字左右。背景是内容运营，本周发布专题并提升转化。"),
    ("渠道拓展", "生成一份周报，包含背景、本周工作、下周计划，300字左右。背景是渠道拓展，本周新增合作伙伴并评估渠道质量。"),
    ("技术支持", "生成一份周报，包含背景、本周工作、下周计划，300字左右。背景是技术支持，本周解决高优先级故障并完善知识库。"),
]


LOG.write_text("", encoding="utf-8")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.on("console", lambda msg: log(f"console {msg.type}: {msg.text}"))
    page.on("request", lambda req: ("/api/doc/" in req.url and log(f"request {req.method} {req.url}")))
    page.on("response", lambda resp: ("/api/doc/" in resp.url and log(f"response {resp.status} {resp.url}")))

    for idx, (title, instruction) in enumerate(cases, 1):
        page.goto(BASE, wait_until="domcontentloaded")
        page.wait_for_selector("textarea", timeout=20000)
        page.wait_for_timeout(500)
        # wait for doc id to be ready
        for _ in range(20):
            if get_doc_id(page):
                break
            page.wait_for_timeout(300)
        log(f"case {idx}: doc_id={get_doc_id(page)}")
        page.fill("textarea", instruction)
        click_button(page, SEND_BTN)
        log(f"case {idx}: {title} started")

        editor_text = wait_doc_text(page, timeout_s=240)
        ok = all(k in editor_text for k in REQ_SECTIONS)
        if not ok:
            log(f"case {idx}: editor missing required sections (len={len(editor_text)})")
        else:
            log(f"case {idx}: editor ok (len={len(editor_text)})")

        click_button(page, SAVE_BTN)
        page.wait_for_timeout(500)
        safe = re.sub(r"[\\/:*?\"<>|]+", "", title)[:24] or "case"
        out_path = OUT / f"ui_round_{idx:02d}_{safe}.docx"
        try:
            with page.expect_download(timeout=60000) as download_info:
                click_button(page, EXPORT_BTN)
            download = download_info.value
            download.save_as(str(out_path.resolve()))
            log(f"case {idx}: saved {out_path.name}")
        except Exception as exc:
            log(f"case {idx}: export failed: {exc}")
            doc_id = get_doc_id(page)
            if doc_id:
                try:
                    resp = page.request.get(f"{BASE}download/{doc_id}.docx")
                    if resp.ok:
                        out_path.write_bytes(resp.body())
                        log(f"case {idx}: saved via direct download {out_path.name}")
                except Exception as exc2:
                    log(f"case {idx}: direct download failed: {exc2}")

    browser.close()

print("done")
