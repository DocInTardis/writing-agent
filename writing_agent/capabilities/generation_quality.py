"""Generation quality capability helpers."""

from __future__ import annotations

from collections import Counter


def check_generation_quality(text: str, target_chars: int = 0) -> list[str]:
    issues: list[str] = []
    stripped = text.strip()
    if len(stripped) < 50:
        issues.append("生成内容过短，少于 50 个字符")
    if not stripped:
        issues.append("生成内容为空")

    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if len(lines) != len(set(lines)):
        line_counts = Counter(lines)
        duplicates = [line for line, count in line_counts.items() if count > 1]
        if duplicates:
            issues.append(f"检测到重复内容：{len(duplicates)} 行重复")

    if "##" not in text and "#" not in text:
        issues.append("缺少标题结构")

    if target_chars > 0:
        actual_chars = len(text)
        deviation = abs(actual_chars - target_chars) / target_chars
        if deviation > 0.3:
            issues.append(
                f"字数偏差较大：目标 {target_chars} 字，实际 {actual_chars} 字（偏差 {deviation * 100:.1f}%）"
            )

    if stripped and stripped[-1] in [",", "，", "...", "…"]:
        issues.append("文档结尾不完整")

    # Citation format check
    import re as _re
    bad_citations = _re.findall(r'\[\s*@\s*[\s\]]', text)
    if bad_citations:
        issues.append(f"引用格式异常：发现 {len(bad_citations)} 处不规范的引用标记")

    # Coherence check: excessive short sentences or orphaned bullets
    sentence_fragments = [ln for ln in lines if len(ln) < 10 and not ln.startswith("#")]
    if len(sentence_fragments) > 5:
        issues.append(f"逻辑连贯性警告：发现 {len(sentence_fragments)} 处过短句子，可能影响阅读连贯性")

    # Grammar check: consecutive punctuation
    consecutive_punct = _re.findall(r'[，。！？；：,;:!?\.]\s*[，。！？；：,;:!?\.]', text)
    if consecutive_punct:
        issues.append(f"标点使用异常：发现 {len(consecutive_punct)} 处连续标点")

    return issues


def looks_like_prompt_echo(text: str, instruction: str) -> bool:
    src = (text or "").strip()
    if not src:
        return True

    lower = src.lower()
    phrases = [
        "you are a writing assistant",
        "output markdown only",
        "user requirement",
        "must include",
    ]
    hit = sum(1 for phrase in phrases if phrase in lower)
    if hit >= 2:
        return True
    if lower.startswith("you are ") and "assistant" in lower:
        return True

    prompt_markers = (
        "revision request:",
        "<execution_plan>",
        "<original_document>",
        "<task>revise_full_document</task>",
        "<revised_markdown>",
        "<revised_document>",
    )
    if any(marker in lower for marker in prompt_markers):
        return True

    if src.startswith("你是") and ("助手" in src or "模型" in src or "写作" in src):
        return True

    short_instruction = instruction.strip()[:12]
    if short_instruction and short_instruction in src and "requirement" in lower:
        return True
    if len(src) < 200 and ("requirement" in lower or "markdown" in lower):
        return True
    return False


__all__ = [name for name in globals() if not name.startswith("__")]
