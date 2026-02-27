"""Graph Text Sanitize Domain module.

This module belongs to `writing_agent.v2` in the writing-agent codebase.
"""

from __future__ import annotations

import re
from typing import Callable


def strip_chatty_closings(text: str, *, banned_phrases: list[str] | None = None) -> str:
    if not text:
        return text
    banned = banned_phrases or []
    paras = re.split(r"\n\s*\n+", text)
    kept = []
    for para in paras:
        value = para.strip()
        if not value:
            continue
        if any(phrase in value for phrase in banned):
            continue
        kept.append(para)
    return "\n\n".join(kept)


def compact_list_spacing(text: str) -> str:
    lines = (text or "").split("\n")

    def is_list_line(line: str) -> bool:
        value = (line or "").strip()
        if not value:
            return False
        if re.match(r"^\d+[.\uFF0E\u3001\)]\s+", value):
            return True
        if re.match(r"^[一二三四五六七八九十]+[.\u3001\)]\s+", value):
            return True
        if re.match(r"^[\u2022\u00B7]\s+", value):
            return True
        return False

    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.strip():
            out.append(line)
            i += 1
            continue
        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        prev = ""
        for k in range(len(out) - 1, -1, -1):
            if out[k].strip():
                prev = out[k]
                break
        next_line = lines[j] if j < len(lines) else ""
        if prev and next_line and is_list_line(prev) and is_list_line(next_line):
            i = j
            continue
        out.append("")
        i = j
    return "\n".join(out)


def strip_markdown_noise(text: str) -> str:
    src = text or ""
    src = re.sub(r"```[^\n]*", "", src)
    src = src.replace("```", "")
    src = src.replace("`", "")

    def scrub_line(line: str) -> str:
        raw = line
        if re.match(r"^\s*#{1,3}\s*$", raw):
            return ""
        if re.match(r"^\s*#{4,}\s+", raw):
            raw = re.sub(r"^\s*#{4,}\s+", "", raw)
        raw = re.sub(r"^\s*[*\-\u2013]\s+", "", raw)
        raw = re.sub(r"(?<!\*)\*(?!\*)", "", raw)
        raw = re.sub(r"\s*#+\s*$", "", raw)
        return raw

    lines = [scrub_line(line) for line in src.split("\n")]
    return "\n".join(lines)


def normalize_punctuation(text: str) -> str:
    src = text or ""
    punct_map = {",": "，", ".": "。", "?": "？", "!": "！", ":": "：", ";": "；"}

    def repl_left(match: re.Match[str]) -> str:
        return f"{match.group(1)}{punct_map.get(match.group(2), match.group(2))}"

    def repl_right(match: re.Match[str]) -> str:
        return f"{punct_map.get(match.group(1), match.group(1))}{match.group(2)}"

    src = re.sub(r"([\u4e00-\u9fff])([,.;:!?])", repl_left, src)
    src = re.sub(r"([,.;:!?])([\u4e00-\u9fff])", repl_right, src)
    return src


def is_short_tail(text: str) -> bool:
    value = (text or "").strip()
    if not value:
        return False
    if len(value) > 4:
        return False
    return bool(re.fullmatch(r"[\u4e00-\u9fffA-Za-z0-9]+", value))


def should_merge_tail(prev_line: str, line: str) -> bool:
    if not prev_line or not line:
        return False
    if not is_short_tail(line):
        return False
    prev = prev_line.strip()
    if re.match(r"^#{1,3}\s+\S", prev):
        return True
    if len(prev) <= 18 and re.search(r"[\u4e00-\u9fff]$", prev) and not re.search(r"[。！？!?;；：:]$", prev):
        return True
    return False


def clean_generated_text(text: str, *, should_merge_tail_fn: Callable[[str, str], bool]) -> str:
    src = (text or "").replace("\r", "")
    lines = src.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        raw = lines[i]
        token = raw.strip()
        if not token:
            out.append("")
            i += 1
            continue
        if token in {"#", "##", "###"}:
            if i + 1 < len(lines):
                nxt = lines[i + 1].strip()
                if nxt:
                    out.append(f"{token} {nxt}")
                    i += 2
                    continue
            i += 1
            continue
        if out and should_merge_tail_fn(out[-1], token):
            out[-1] = out[-1].rstrip() + token
            i += 1
            continue
        out.append(raw)
        i += 1
    src = "\n".join(out)
    src = re.sub(r"(?<!\*)\*(?!\*)", "", src)
    src = re.sub(r"(?m)^\s*[*\-\u2013]\s+", "", src)
    src = re.sub(r"\n{3,}", "\n\n", src)
    return src.strip()


def sanitize_output_text(
    text: str,
    *,
    meta_phrases: list[str],
    has_cjk: Callable[[str], bool],
    is_mostly_ascii_line: Callable[[str], bool],
    banned_phrases: list[str],
) -> str:
    value = (text or "").replace("\r", "")
    value = re.sub(r"\[\s*(?:待补充|todo|tbd)[^\]]*\]", "", value, flags=re.IGNORECASE)
    value = re.sub(r"[（(]\s*(?:待补充|todo|tbd)[^）)]*[)）]", "", value, flags=re.IGNORECASE)
    value = strip_markdown_noise(value)
    value = re.sub(r"<[^>]+>", "", value)
    value = value.replace("&nbsp;", " ")
    value = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", value)
    value = strip_chatty_closings(value, banned_phrases=banned_phrases)
    filtered_lines: list[str] = []
    for line in value.split("\n"):
        if is_mostly_ascii_line(line) and not has_cjk(line):
            continue
        if re.match(r"^#{1,3}\s*[?？]{2,}\s*$", line):
            line = "## 参考文献"
        elif re.match(r"^[?？]{2,}\s*$", line):
            line = "参考文献"
        filtered_lines.append(line)
    value = "\n".join(filtered_lines)
    for phrase in meta_phrases:
        if not phrase:
            continue
        value = value.replace(phrase, "")
    value = normalize_punctuation(value)
    value = re.sub(r"[ \t]+", " ", value)
    value = compact_list_spacing(value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()
