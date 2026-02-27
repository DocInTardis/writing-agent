# coding: utf-8
"""Ui Templates Figures Revise Test command utility.

This script is part of the writing-agent operational toolchain.
"""

from pathlib import Path
from playwright.sync_api import sync_playwright
import json
import os
import re
import time

BASE = "http://127.0.0.1:8000/"
OUT = Path(".data") / "out"
OUT.mkdir(parents=True, exist_ok=True)
LOG = OUT / "ui_templates_figures_revise_test.log"


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
        return length_hint or "4000字"
    m = re.search(r"\u201C(.+?)\u201D", q)
    if m:
        return m.group(1)
    return "默认"


def parse_figure_types(text: str) -> set[str]:
    found: set[str] = set()
    for raw in re.findall(r"\[\[\s*FIGURE\s*:\s*(\{[\s\S]*?\})\s*\]\]", text, flags=re.IGNORECASE):
        try:
            data = json.loads(raw)
        except Exception:
            continue
        t = str(data.get("type") or "").strip().lower()
        if t:
            found.add(t)
    return found


def build_missing_blocks(missing: list[str]) -> str:
    blocks = []
    blocks.append("附录 图表")
    for t in missing:
        if t == "flow":
            blocks.append(
                '[[FIGURE:{"type":"flow","caption":"工资处理业务流程","data":{"nodes":["需求输入","数据校验","薪资核算","审批确认","工资发放"],"edges":[{"src":"n1","dst":"n2"},{"src":"n2","dst":"n3"},{"src":"n3","dst":"n4"},{"src":"n4","dst":"n5"}]}}]]'
            )
        elif t == "er":
            blocks.append(
                '[[FIGURE:{"type":"er","caption":"工资管理系统ER图","data":{"entities":[{"name":"员工","attributes":["员工ID","姓名","部门","岗位"]},{"name":"工资单","attributes":["工资单ID","月份","应发","实发"]},{"name":"考勤","attributes":["考勤ID","月份","缺勤天数"]}],"relations":[{"left":"员工","right":"工资单","label":"生成","cardinality":"1..n"},{"left":"员工","right":"考勤","label":"关联","cardinality":"1..n"}]}}]]'
            )
        elif t == "bar":
            blocks.append(
                '[[FIGURE:{"type":"bar","caption":"品类库存量对比","data":{"labels":["A类","B类","C类","D类"],"values":[120,80,60,45]}}]]'
            )
        elif t == "line":
            blocks.append(
                '[[FIGURE:{"type":"line","caption":"近五周周转率趋势","data":{"labels":["W1","W2","W3","W4","W5"],"series":{"name":"周转率","values":[1.2,1.4,1.1,1.6,1.8]}}}]]'
            )
        elif t == "pie":
            blocks.append(
                '[[FIGURE:{"type":"pie","caption":"库存占比结构","data":{"segments":[{"label":"原材料","value":35},{"label":"半成品","value":25},{"label":"成品","value":40}]}}]]'
            )
        elif t == "timeline":
            blocks.append(
                '[[FIGURE:{"type":"timeline","caption":"项目里程碑时间线","data":{"events":[{"time":"第1周","label":"需求澄清"},{"time":"第2周","label":"原型评审"},{"time":"第4周","label":"核心开发"},{"time":"第6周","label":"联调上线"}]}}]]'
            )
        elif t == "sequence":
            blocks.append(
                '[[FIGURE:{"type":"sequence","caption":"选课提交时序图","data":{"participants":["学生端","选课服务","课程库"],"messages":[{"from":"学生端","to":"选课服务","text":"提交选课"},{"from":"选课服务","to":"课程库","text":"校验名额"},{"from":"课程库","to":"选课服务","text":"返回结果"},{"from":"选课服务","to":"学生端","text":"确认反馈"}]}}]]'
            )
    return "\n\n".join(blocks)


def build_fallback_text() -> str:
    paras = [
        "工资管理系统课程报告",
        "第1章 课题背景与目标",
        "本项目围绕企业薪资核算与发放流程展开，目标是建立稳定、可审计、易扩展的工资管理系统。",
        "系统需要覆盖员工信息、薪资结构、考勤与绩效、审批与发放等关键环节，并保证数据一致性与可追溯性。",
        "第2章 需求与范围",
        "功能需求包括：员工档案维护、薪资规则配置、考勤导入、自动核算、审批流与发放记录管理。",
        "非功能需求包括：权限分级、日志审计、数据备份与恢复、以及可扩展的接口能力。",
        "第3章 总体设计",
        "总体架构采用分层模式，划分为表现层、业务层与数据层，核心服务以清晰的模块边界保证可维护性。",
        "关键流程涵盖数据录入、核算校验、审批与发放闭环，流程清晰且可度量。",
        "第4章 数据设计",
        "核心实体包含员工、工资单、考勤、绩效与审批记录，并通过主外键关系保证薪资数据的一致性。",
        "第5章 实现与测试",
        "实现阶段重点关注规则引擎与批量核算效率，测试阶段覆盖正确性、性能与异常场景。",
        "第6章 结论",
        "系统在准确性、可控性与可扩展性方面达到课程目标，具备进一步工程化落地的基础。",
    ]
    return "\n\n".join(paras).strip() + "\n"


env_templates = (os.environ.get("UI_TEMPLATES") or "").strip()
if env_templates:
    templates = [Path("templates") / s.strip() for s in env_templates.split("|") if s.strip()]
else:
    templates = [
        Path("templates") / "附件4：广东工业大学本科生毕业设计（论文）开题报告.docx",
        Path("templates") / "一种可选的章节结构（仅供参考）.docx",
        Path("templates") / "专业项目设计(1).docx",
    ]

instruction = (
    "写一份工资管理系统课程报告，约4000字，默认格式。"
    "必须包含流程图(flow)、ER图(er)、柱状图(bar)、折线图(line)、饼图(pie)、时间线(timeline)、时序图(sequence)。"
    "每种图都使用 [[FIGURE:{...}]] 标记并填写具体数据。"
)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()

    for t in templates:
        page.goto(BASE, wait_until="domcontentloaded")
        page.wait_for_selector("#instruction")
        log(f"page loaded for {t.name}")

        page.click("#btnAttach")
        page.click("#btnUpload")
        page.set_input_files("#uploadFile", str(t.resolve()))
        log(f"file uploaded {t.name}")

        try:
            page.wait_for_selector("#modalRoot:not(.hidden)", timeout=180000)
            buttons = page.locator("#modalFoot button")
            if buttons.count() >= 3:
                buttons.nth(2).click(force=True)
            else:
                buttons.first.click(force=True)
            page.wait_for_timeout(400)
        except Exception:
            log("upload confirm modal not shown")
        close_modal(page)

        page.wait_for_function("() => !document.querySelector('#instruction').disabled", timeout=300000)

        page.fill("#instruction", instruction)
        close_modal(page)
        page.click("#btnGenerate")
        log("sent instruction")

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
            answer = answer_for(question, "4000字")
            page.fill("#instruction", answer)
            close_modal(page)
            page.click("#btnGenerate")
            log(f"answered {answer}")

        done = False
        max_ticks = int(os.environ.get("UI_MAX_TICKS", "600"))
        for i in range(max_ticks):
            flow = page.evaluate("() => document.querySelector('#flowStatus')?.textContent || ''")
            status = page.evaluate("() => document.querySelector('#docStatus')?.textContent || ''")
            if i % 10 == 0:
                log(f"tick {i}: flow={flow} status={status}")
            if "完成" in flow:
                done = True
                break
            page.wait_for_timeout(3000)
        if not done:
            log("generation not completed; continue with manual append")

        text = page.evaluate("() => document.querySelector('#source')?.value || ''")
        if len(text.strip()) < 800:
            fallback = build_fallback_text()
            page.evaluate(
                """
(val) => {
  const ta = document.querySelector('#source');
  if (!ta) return;
  ta.value = val;
  ta.dispatchEvent(new Event('input', { bubbles: true }));
}
""",
                fallback,
            )
            text = fallback
            log("fallback text applied")
        found = parse_figure_types(text)
        needed = {"flow", "er", "bar", "line", "pie", "timeline", "sequence"}
        missing = sorted(needed - found)
        if missing:
            extra = build_missing_blocks(missing)
            merged = (text.strip() + "\n\n" + extra).strip() + "\n"
            page.evaluate(
                """
(val) => {
  const ta = document.querySelector('#source');
  if (!ta) return;
  ta.value = val;
  ta.dispatchEvent(new Event('input', { bubbles: true }));
}
""",
                merged,
            )
            close_modal(page)
            page.click('.tab[data-tab="preview"]')
            close_modal(page)
            page.click('.tab[data-tab="edit"]')
            log(f"appended missing figures: {','.join(missing)}")

        # selection revise flow
        revised = False
        try:
            btn_state = page.evaluate(
                "() => ({ stopDisabled: document.querySelector('#btnStop')?.disabled, reviseDisabled: document.querySelector('#btnRevise')?.disabled })"
            )
            log(f"buttons: stopDisabled={btn_state.get('stopDisabled')} reviseDisabled={btn_state.get('reviseDisabled')}")
        except Exception:
            pass
        try:
            page.click("#btnStop", force=True)
            page.wait_for_timeout(800)
            page.wait_for_function("() => document.querySelector('#btnStop')?.disabled === true", timeout=15000)
        except Exception:
            pass
        try:
            page.fill("#instruction", "请润色全文，保证表述更专业、删除口语化表达。")
            close_modal(page)
            page.click("#btnRevise")
            page.wait_for_selector("#modalRoot:not(.hidden)", timeout=180000)
            page.locator("#modalRoot button", has_text="应用修订").click(force=True)
            page.wait_for_timeout(1500)
            log("revise applied")
            revised = True
        except Exception:
            try:
                status = page.evaluate("() => document.querySelector('#docStatus')?.textContent || ''")
                log(f"revise modal not shown; status={status}")
            except Exception:
                log("revise modal not shown")

        stamp = time.strftime("%Y%m%d_%H%M%S")
        name = re.sub(r"[\\\\/:*?\"<>|]+", "", t.stem)[:24] or "template"
        out_path = OUT / f"ui_template_figures_{name}_{stamp}.docx"
        close_modal(page)
        with page.expect_download() as download_info:
            page.click("#btnDownload")
        download = download_info.value
        download.save_as(str(out_path.resolve()))
        log(f"saved {out_path.name}")

    browser.close()
