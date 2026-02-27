# -*- coding: utf-8 -*-
"""Ui E2E 1000 command utility.

This script is part of the writing-agent operational toolchain.
"""

import asyncio
import json
import os
import random
import re
import socket
import subprocess
import time
from pathlib import Path

from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError


def pick_port(host: str, base: int, tries: int = 20) -> int:
    for i in range(tries):
        port = base + i
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, port))
                return port
            except OSError:
                continue
    return base


ROOT = Path(__file__).resolve().parents[1]
PY = ROOT / ".venv" / "Scripts" / "python.exe"

HOST = "127.0.0.1"
PORT = 8010
PORT_TRIES = 20
BATCH_LIMIT = int(os.environ.get("WRITING_AGENT_UI_BATCH", "1000"))
WORKERS = int(os.environ.get("WRITING_AGENT_UI_WORKERS", "4"))
PORT = pick_port(HOST, PORT, PORT_TRIES)
BASE = f"http://{HOST}:{PORT}/"
SAMPLE_DIR = ROOT / "test_samples"
PROGRESS_FILE = ROOT / "test_samples" / "progress.json"
SUMMARY_FILE = ROOT / "test_samples" / "score_summary.json"
SAMPLE_DIR.mkdir(parents=True, exist_ok=True)

PROMPTS = [
    "给领导看的项目总结，强调结果、风险、下一步计划，语气简洁",
    "毕业设计报告：校园二手交易平台，强调系统架构和数据库设计，1000字以内",
    "客户方案，突出实施路径与里程碑，避免夸大效果",
    "PRD：新用户引导功能，明确需求列表、非功能需求",
    "可行性分析：体育管理系统，包含成本收益、风险评估",
    "调研报告：大学生运动习惯，说明方法与样本，结果与建议",
]

PROMPT_TYPES = [
    ("summary", PROMPTS[0]),
    ("thesis", PROMPTS[1]),
    ("plan", PROMPTS[2]),
    ("prd", PROMPTS[3]),
    ("feasibility", PROMPTS[4]),
    ("research", PROMPTS[5]),
]
REVISE_PROMPTS = [
    "所有标题换成黑体三号，正文不变",
    "这一节需要一个流程图",
    "参考文献错误，需要修正并补充",
    "语气更正式，减少口语",
]

ANSWER_MAP = [
    (re.compile(r"标题|题目"), "校园二手交易平台系统报告"),
    (re.compile(r"字数|页数|长度"), "800字"),
    (re.compile(r"用途|场景"), "课程报告"),
    (re.compile(r"受众|对象|读者"), "老师"),
    (re.compile(r"输出|形式|类型"), "报告"),
    (re.compile(r"语气|风格"), "正式、简洁"),
    (re.compile(r"避免|不希望|禁忌"), "不夸大效果"),
]


def load_progress():
    if PROGRESS_FILE.exists():
        try:
            data = json.loads(PROGRESS_FILE.read_text(encoding="utf-8"))
            done = int(data.get("done", 0))
            scores = list(data.get("scores", []))
            saved = list(data.get("saved", []))
            if done > len(scores):
                done = len(scores)
            if done < 0:
                done = 0
            return {"done": done, "scores": scores, "saved": saved}
        except Exception:
            return {"done": 0, "scores": [], "saved": []}
    return {"done": 0, "scores": [], "saved": []}


def save_progress(done, scores, saved):
    PROGRESS_FILE.write_text(
        json.dumps({"done": done, "scores": scores, "saved": list(saved)}, ensure_ascii=False),
        encoding="utf-8",
    )


def save_summary(done, scores, saved):
    avg = sum(scores) / max(1, len(scores))
    SUMMARY_FILE.write_text(
        json.dumps(
            {
                "done": done,
                "avg": avg,
                "min": min(scores) if scores else None,
                "max": max(scores) if scores else None,
                "scores": scores,
                "samples": sorted(saved),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def start_server():
    env = os.environ.copy()
    env.update(
        {
            "WRITING_AGENT_HOST": HOST,
            "WRITING_AGENT_PORT": str(PORT),
            "WRITING_AGENT_TARGET_TOTAL_CHARS": "450",
            "WRITING_AGENT_FAST_DRAFT": "1",
            "WRITING_AGENT_DRAFT_MAX_MODELS": "1",
            "WRITING_AGENT_PERF_MODE": "1",
            "WRITING_AGENT_SECTION_TIMEOUT_S": "15",
            "WRITING_AGENT_ANALYSIS_TIMEOUT_S": "5",
            "WRITING_AGENT_EXTRACT_TIMEOUT_S": "5",
            "WRITING_AGENT_SECTION_CONTINUE_ROUNDS": "0",
            "WRITING_AGENT_VALIDATE_PLAN": "0",
            "WRITING_AGENT_ENSURE_MIN_LENGTH": "0",
            "WRITING_AGENT_EVIDENCE_ENABLED": "0",
            "WRITING_AGENT_RAG_ENABLED": "0",
            "WRITING_AGENT_USE_OLLAMA": "0",
        }
    )
    return subprocess.Popen([str(PY), "-m", "writing_agent.launch"], env=env)


def wait_ready():
    import urllib.request

    for _ in range(60):
        try:
            with urllib.request.urlopen(BASE, timeout=2) as r:
                if r.status < 500:
                    return True
        except Exception:
            time.sleep(0.5)
    return False


def score_text(text: str) -> int:
    n = len(re.sub(r"\s+", "", text))
    has_h2 = bool(re.search(r"(?m)^##\s+", text))
    score = 60
    if has_h2:
        score += 15
    if n >= 400:
        score += 15
    if re.search(r"参考文献|参考文獻", text):
        score += 10
    return min(100, score)


def answer_for(question: str) -> str:
    for rx, ans in ANSWER_MAP:
        if rx.search(question):
            return ans
    return "默认"


async def run_case(page, lock, state):
    ptype, prompt = random.choice(PROMPT_TYPES)
    await page.goto(BASE, wait_until="domcontentloaded")
    await page.fill("#instruction", prompt)
    await page.click("#btnGenerate")

    for _ in range(3):
        await asyncio.sleep(0.2)
        btn = await page.query_selector("#btnGenerate")
        if btn and (await btn.get_attribute("data-mode")) == "reply":
            msgs = await page.query_selector_all("#chatHistory .chat-msg.system .chat-text")
            q = await msgs[-1].inner_text() if msgs else ""
            ans = answer_for(q)
            await page.fill("#instruction", ans)
            await page.click("#btnGenerate")
        else:
            break

    try:
        await page.wait_for_function(
            "() => {"
            "const stopBtn = document.querySelector('#btnStop');"
            "const active = document.querySelector('#graph .node.active');"
            "const state = active ? active.getAttribute('data-state') : '';"
            "return (stopBtn && stopBtn.disabled) || state === 'DONE';"
            "}",
            timeout=6000,
        )
    except PlaywrightTimeoutError:
        pass

    for _ in range(2):
        try:
            if not await page.is_enabled("#btnRevise"):
                continue
            await page.fill("#instruction", random.choice(REVISE_PROMPTS))
            await page.click("#btnRevise")
            try:
                await page.wait_for_selector(".modal-root:not(.hidden)", timeout=3000)
                apply_btn = await page.query_selector(".modal-root .btn.primary")
                if apply_btn:
                    await apply_btn.click()
            except PlaywrightTimeoutError:
                pass
        except Exception:
            pass

    app = await page.query_selector(".app")
    doc_id = await app.get_attribute("data-doc-id") if app else ""
    if not doc_id:
        return

    resp = await page.request.get(f"http://{HOST}:{PORT}/api/doc/{doc_id}")
    data = await resp.json()
    text = data.get("text", "")
    score = score_text(text)

    async with lock:
        state["results"].append(score)
        if ptype not in state["saved"]:
            try:
                dl = await page.request.get(f"http://{HOST}:{PORT}/download/{doc_id}.docx")
                out_path = SAMPLE_DIR / f"{ptype}_{doc_id}.docx"
                out_path.write_bytes(await dl.body())
                state["saved"].add(ptype)
            except Exception:
                pass
        state["done"] += 1
        save_progress(state["done"], state["results"], state["saved"])


async def run_batch(done0, limit, results, saved):
    lock = asyncio.Lock()
    state = {"done": done0, "results": results, "saved": saved}

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        pages = [await browser.new_page() for _ in range(max(1, WORKERS))]

        queue = asyncio.Queue()
        for _ in range(limit):
            queue.put_nowait(True)

        async def worker(page):
            while True:
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                try:
                    await run_case(page, lock, state)
                except Exception:
                    pass
                finally:
                    queue.task_done()

        await asyncio.gather(*(worker(p) for p in pages))
        for page in pages:
            await page.close()
        await browser.close()

    return state["done"], state["results"], state["saved"]


def main():
    server = start_server()
    try:
        if not wait_ready():
            print("Server not ready")
            return 1
        if os.environ.get("WRITING_AGENT_UI_RESET") == "1":
            prog = {"done": 0, "scores": [], "saved": []}
        else:
            prog = load_progress()
        save_progress(int(prog.get("done", 0)), list(prog.get("scores", [])), set(prog.get("saved", [])))
        results = list(prog.get("scores", []))
        done0 = int(prog.get("done", 0))
        saved = set(prog.get("saved", []))

        end = min(1000, done0 + BATCH_LIMIT)
        target = end - done0
        if target <= 0:
            save_summary(done0, results, saved)
            print("Avg score:", sum(results) / max(1, len(results)))
            print("Samples saved:", ", ".join(sorted(saved)))
            return 0

        done, results, saved = asyncio.run(run_batch(done0, target, results, saved))

        save_progress(done, results, saved)
        save_summary(done, results, saved)
        avg = sum(results) / max(1, len(results))
        print("Avg score:", avg)
        print("Samples saved:", ", ".join(sorted(saved)))
        if done >= 1000:
            try:
                PROGRESS_FILE.unlink()
            except Exception:
                pass
        return 0
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
