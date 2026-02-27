"""Extract Prefs Test command utility.

This script is part of the writing-agent operational toolchain.
"""

import json
import re
import sys
import time
import urllib.request


BASE_URL = "http://127.0.0.1:8000"


def http_json(method: str, url: str, data: dict | None = None) -> dict:
    body = None
    headers = {}
    if data is not None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=8) as resp:
        raw = resp.read().decode("utf-8")
        return json.loads(raw)


def get_doc_id() -> str:
    req = urllib.request.Request(f"{BASE_URL}/", method="GET")
    with urllib.request.urlopen(req, timeout=8) as resp:
        final_url = resp.geturl()
    m = re.search(r"/workbench/([a-f0-9]{16,})", final_url)
    if not m:
        raise RuntimeError(f"Failed to parse doc id from {final_url}")
    return m.group(1)


def build_cases() -> list[dict]:
    titles = [
        "工资管理系统",
        "图书管理系统",
        "课程选课系统",
        "人事管理系统",
        "在线考试系统",
        "仓储管理系统",
        "车辆管理系统",
        "宿舍管理系统",
        "库存管理系统",
        "报销管理系统",
        "会议管理系统",
        "学生成绩管理系统",
        "医院挂号系统",
        "订单管理系统",
        "客户关系管理系统",
        "设备巡检系统",
        "售后服务系统",
        "绩效考核系统",
        "资产管理系统",
        "档案管理系统",
        "请假审批系统",
        "招生管理系统",
        "排课管理系统",
        "智慧校园平台",
        "电商订单系统",
        "物流调度系统",
        "生产管理系统",
        "项目跟踪系统",
        "合同管理系统",
        "采购管理系统",
        "运维监控系统",
        "工单处理系统",
        "设备维护系统",
        "风险评估系统",
        "安全巡检系统",
        "网站内容管理系统",
        "会员管理系统",
        "积分管理系统",
        "考勤管理系统",
        "绩效评估系统",
    ]
    purposes = [
        "课程报告",
        "课程设计",
        "毕业设计",
        "项目总结",
        "调研报告",
        "可行性报告",
        "参考作用",
        "课程汇报",
        "阶段总结",
        "项目复盘",
    ]
    lengths = [3000, 5000, 6000, 8000, 12000]
    pages = [8, 10, 12, 15, 20]
    formats = ["默认格式", "按默认", "不需要模板", "无特殊格式", "默认", "不用模板", "按默认格式"]
    tones = ["写一份", "写个", "生成", "帮我写", "给我写", "出一份", "产出", "做一份", "准备一份"]
    templates = [
        "我要{tone}{title}报告，{purpose}，约{len}字，{fmt}。",
        "{tone}{title}报告 {len}字 {purpose} {fmt}",
        "{tone}{title}的报告，{purpose}，字数{len}，{fmt}",
        "{tone}{title}报告，{len}字左右，用于{purpose}，{fmt}",
        "请{tone}{title}报告，用途{purpose}，篇幅{len}字，{fmt}",
        "{tone}{title}报告，{purpose}，大概{len}字，{fmt}",
        "我要{title}报告，{purpose}，{len}字左右，{fmt}",
        "{tone}{title}报告，{purpose}，目标{len}字，{fmt}",
        "{tone}{title}报告，{len}字，{purpose}，{fmt}",
        "给我{title}报告，{purpose}，约{len}字，{fmt}",
        "{tone}《{title}》报告，{purpose}，{len}字，{fmt}",
        "{title}报告，{purpose}，{len}字，{fmt}",
        "请{tone}{title}报告，{purpose}，约{pages}页，{fmt}",
        "{tone}{title}报告，{purpose}，篇幅{pages}页，{fmt}",
        "{tone}{title}报告，{purpose}，{pages}页左右，{fmt}",
        "{tone}{title}报告，{purpose}，字数约{len}，{fmt}",
        "{tone}{title}报告，{purpose}，字数{len}，{fmt}",
        "{tone}{title}报告，{purpose}，长度{len}字，{fmt}",
        "{tone}{title}报告，{purpose}，约{pages}页，{fmt}",
    ]
    alt_formats = ["默认", "按默认", "不设模板", "不需模板", "模板随系统", "格式默认"]
    suffixes = ["", "！", "。", "，", "。谢谢", "！麻烦了"]
    colloquials = [
        "整一份{title}报告，{purpose}，{len}字，{fmt}",
        "{title}报告来一份，{purpose}，{len}字，{fmt}",
        "麻烦写个{title}报告，{purpose}，{len}字，{fmt}",
        "帮忙写{title}报告，{purpose}，{len}字左右，{fmt}",
        "想要{title}报告，{purpose}，{len}字，{fmt}",
        "写个{title}的吧，{purpose}，{len}字，{fmt}",
        "给我出个{title}报告，{purpose}，{len}字，{fmt}",
        "弄份{title}报告，{purpose}，{len}字，{fmt}",
    ]
    typos = [
        "{tone}{title}报高，{purpose}，字数{len}，{fmt}",
        "{tone}{title}宝告，{purpose}，字数{len}，{fmt}",
        "{tone}{title}报靠，{purpose}，字数{len}，{fmt}",
        "{tone}{title}保告，{purpose}，字数{len}，{fmt}",
        "{tone}{title}抱告，{purpose}，字数{len}，{fmt}",
    ]
    ellipsis = [
        "{tone}{title}... {purpose} ... {len}字 ... {fmt}",
        "{title}报告 {purpose} ... 字数{len} ... {fmt}",
        "写{title}报告 {purpose} {len}字",
        "{title}报告 {len}字 {purpose}",
        "{title} {len}字 {purpose}",
    ]
    cases = []
    for i, title in enumerate(titles):
        purpose = purposes[i % len(purposes)]
        length = lengths[i % len(lengths)]
        pages_n = pages[i % len(pages)]
        fmt = formats[i % len(formats)]
        tone = tones[i % len(tones)]
        for tmpl in templates:
            text = tmpl.format(title=title, purpose=purpose, len=length, fmt=fmt, pages=pages_n, tone=tone)
            text = text + suffixes[i % len(suffixes)]
            expected = {
                "title": title,
                "purpose": purpose,
                "length": length if "字" in text else None,
                "pages": pages_n if "页" in text else None,
            }
            cases.append({"text": text, "expected": expected})
            if len(cases) >= 2000:
                return cases
        for j, fmt2 in enumerate(alt_formats):
            text = f"{tone}{title}报告，{purpose}，字数{length}，{fmt2}"
            expected = {
                "title": title,
                "purpose": purpose,
                "length": length,
                "pages": None,
            }
            cases.append({"text": text, "expected": expected})
            if len(cases) >= 2000:
                return cases
        for tmpl in colloquials:
            text = tmpl.format(title=title, purpose=purpose, len=length, fmt=fmt)
            expected = {
                "title": title,
                "purpose": purpose,
                "length": length,
                "pages": None,
            }
            cases.append({"text": text, "expected": expected})
            if len(cases) >= 2000:
                return cases
        for tmpl in typos:
            text = tmpl.format(title=title, purpose=purpose, len=length, fmt=fmt, tone=tone)
            expected = {
                "title": title,
                "purpose": purpose,
                "length": length,
                "pages": None,
            }
            cases.append({"text": text, "expected": expected})
            if len(cases) >= 2000:
                return cases
        for tmpl in ellipsis:
            text = tmpl.format(title=title, purpose=purpose, len=length, fmt=fmt, tone=tone)
            expected = {
                "title": title,
                "purpose": purpose,
                "length": length,
                "pages": None,
            }
            cases.append({"text": text, "expected": expected})
            if len(cases) >= 2000:
                return cases
    idx = 0
    while len(cases) < 2000:
        title = titles[idx % len(titles)]
        purpose = purposes[idx % len(purposes)]
        length = lengths[idx % len(lengths)]
        text = f"{title} {length}字 {purpose}"
        expected = {"title": title, "purpose": purpose, "length": length, "pages": None}
        cases.append({"text": text, "expected": expected})
        idx += 1
    return cases


def main() -> int:
    doc_id = get_doc_id()
    cases = build_cases()
    results = []
    failures = []
    for idx, case in enumerate(cases, 1):
        text = case["text"]
        expected = case["expected"]
        resp = http_json("POST", f"{BASE_URL}/api/doc/{doc_id}/extract_prefs", {"text": text})
        title = str(resp.get("title") or "")
        prefs = resp.get("generation_prefs") or {}
        purpose = str(prefs.get("purpose") or "")
        mode = str(prefs.get("target_length_mode") or "")
        val = int(prefs.get("target_length_value") or 0)
        ok = True
        reasons = []
        if expected["title"]:
            if expected["title"] not in title and title not in expected["title"]:
                ok = False
                reasons.append(f"title mismatch: {title}")
        if expected["purpose"]:
            if expected["purpose"] not in purpose and purpose not in expected["purpose"]:
                ok = False
                reasons.append(f"purpose mismatch: {purpose}")
        if expected["length"]:
            if mode != "chars" or val != expected["length"]:
                ok = False
                reasons.append(f"length mismatch: mode={mode} val={val}")
        if expected["pages"]:
            if mode != "pages" or val != expected["pages"]:
                ok = False
                reasons.append(f"pages mismatch: mode={mode} val={val}")
        results.append(ok)
        if not ok:
            failures.append({"index": idx, "text": text, "reasons": reasons, "resp": resp})
        time.sleep(0.02)

    total = len(results)
    passed = sum(1 for r in results if r)
    print(f"total={total} passed={passed} failed={total - passed}")
    if failures:
        print("failures (first 10):")
        for f in failures[:10]:
            print(f"- #{f['index']} {f['reasons']} :: {f['text']}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
