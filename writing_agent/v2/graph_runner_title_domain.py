"""Title and instruction-classification helpers for graph runner post-processing."""

from __future__ import annotations

import re
import time

ACK_TOKENS = ("\u81f4\u8c22", "\u611f\u8c22", "\u81f4\u8f9e")


def _normalize_title_line(title: str) -> str:
    s = (title or "").replace("\r", " ").replace("\n", " ").strip()
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", s)
    return s.strip()


def _default_title() -> str:
    stamp = time.strftime("%Y%m%d-%H%M")
    return f"\u81ea\u52a8\u751f\u6210\u6587\u6863-{stamp}"


def _fallback_title_from_instruction(instruction: str) -> str:
    s = (instruction or "").strip().replace("\r", " ").replace("\n", " ")
    if not s:
        return ""
    s = re.sub(r"\s+", " ", s)
    s = re.split(r"[\u3002\uff01\uff1f?!;\uff1b]", s)[0].strip()
    s = re.sub(
        r"^(?:\u751f\u6210|\u5199\u4e00\u4efd?|\u5199|\u5236\u4f5c|\u5e2e\u6211|\u8bf7|\u9700\u8981)\s*",
        "",
        s,
    ).strip()
    if not s:
        return ""
    if len(s) > 20:
        s = s[:20].rstrip()
    return s


def _guess_title(instruction: str) -> str:
    s = (instruction or "").strip().replace("\r", "").replace("\n", " ")
    if not s:
        return ""

    chinese_quoted = re.search(r"\u300a([^\u300b]{2,120})\u300b", s)
    if chinese_quoted:
        return chinese_quoted.group(1).strip()[:60]

    quoted = re.search(r"[\"'\u201c\u201d\u2018\u2019](.{2,80}?)[\"'\u201c\u201d\u2018\u2019]", s)
    if quoted:
        return quoted.group(1).strip()[:40]

    report_like = re.search(
        r"([A-Za-z0-9\u4e00-\u9fff]{2,40})\s*(report|paper|proposal|\u65b9\u6848|\u62a5\u544a|\u8bba\u6587)",
        s,
        flags=re.IGNORECASE,
    )
    if report_like:
        return report_like.group(1).strip()[:40]

    first = s
    for sep in ["\u3002", "\uff01", "\uff1f", ".", "!", "?", ";", "\uff1b"]:
        if sep in first:
            first = first.split(sep, 1)[0]
            break
    first = re.sub(r"\s+", " ", first).strip()
    return first[:40]


def _wants_acknowledgement(instruction: str) -> bool:
    s = (instruction or "").replace(" ", "")
    if not s:
        return False
    return any(token in s for token in ACK_TOKENS)


def _filter_ack_headings(headings: list[str], *, allow_ack: bool) -> list[str]:
    if allow_ack:
        return headings
    return [h for h in headings if all(token not in h for token in ACK_TOKENS)]


def _filter_ack_outline(outline: list[tuple[int, str]], *, allow_ack: bool) -> list[tuple[int, str]]:
    if allow_ack:
        return outline
    return [(lvl, txt) for lvl, txt in outline if all(token not in txt for token in ACK_TOKENS)]


def _is_engineering_instruction(instruction: str) -> bool:
    s = re.sub(r"\s+", "", str(instruction or "").lower())
    if not s:
        return False
    academic_hints = [
        "\u8bba\u6587",
        "\u5b66\u672f",
        "\u6458\u8981",
        "\u5173\u952e\u8bcd",
        "\u5f15\u8a00",
        "\u76f8\u5173\u7814\u7a76",
        "\u53c2\u8003\u6587\u732e",
        "cnki",
        "\u6bd5\u4e1a\u8bbe\u8ba1",
    ]
    if any(h in s for h in academic_hints):
        return False
    strong_engineering_hints = [
        "\u63a5\u53e3\u6587\u6863",
        "api\u6587\u6863",
        "\u7cfb\u7edf\u65b9\u6848",
        "\u67b6\u6784\u8bbe\u8ba1\u6587\u6863",
        "\u5b9e\u65bd\u624b\u518c",
        "\u90e8\u7f72\u624b\u518c",
        "\u8fd0\u7ef4\u624b\u518c",
        "\u6a21\u5757\u8bbe\u8ba1",
        "\u5f00\u53d1\u89c4\u8303",
        "\u5de5\u7a0b\u8bbe\u8ba1\u8bf4\u660e",
    ]
    return any(h in s for h in strong_engineering_hints)
