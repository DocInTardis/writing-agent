"""Block Edit module.

This module belongs to `writing_agent.web` in the writing-agent codebase.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any, Dict, Optional, Tuple

from writing_agent.v2.doc_ir import (
    DocIR,
    Operation,
    apply_ops,
    build_index,
    render_block_text,
    ParagraphBlock,
    ListBlock,
    TableBlock,
    FigureBlock,
)
from writing_agent.v2.inline_ai import InlineAIEngine, InlineContext, InlineOperation


_POLITE_PREFIX_RE = re.compile(
    r"^(?:please|pls|kindly|could you|can you|"
    r"\u8bf7|\u9ebb\u70e6|\u5e2e\u6211|\u8bf7\u5e2e\u6211|\u5e2e\u5fd9)\s*",
    flags=re.IGNORECASE,
)
_DELETE_RE = re.compile(
    r"(?:delete|remove|clear|"
    r"\u5220\u9664|\u79fb\u9664|\u53bb\u6389|\u5220\u6389|\u53bb\u9664)",
    flags=re.IGNORECASE,
)
_REPLACE_RE = re.compile(
    r"(?:replace\s+with|replace\s+to|replace|change\s+to|set\s+to|update\s+to|"
    r"\u6539\u4e3a|\u6539\u6210|\u66ff\u6362\u4e3a|\u6362\u6210|\u8bbe\u7f6e\u4e3a)\s*(?P<content>.+)",
    flags=re.IGNORECASE,
)
_APPEND_RE = re.compile(
    r"(?:append|add|insert|"
    r"\u8ffd\u52a0|\u6dfb\u52a0|\u63d2\u5165|\u8865\u5145|\u8865\u5199)\s*(?P<content>.+)",
    flags=re.IGNORECASE,
)
_PREPEND_RE = re.compile(
    r"(?:prepend|add\s+to\s+start|add\s+to\s+beginning|insert\s+before|"
    r"\u5728?\u524d\u9762|\u5f00\u5934)\s*(?:add|insert|"
    r"\u6dfb\u52a0|\u63d2\u5165|\u589e\u52a0)?\s*(?P<content>.+)",
    flags=re.IGNORECASE,
)

_REWRITE_RE = re.compile(
    r"(?:rewrite|rephrase|improve|polish|summarize|expand|simplify|"
    r"\u91cd\u5199|\u6539\u5199|\u6da6\u8272|\u4f18\u5316|\u7cbe\u7b80|\u7b80\u5316|"
    r"\u603b\u7ed3|\u6982\u62ec|\u7f29\u5199|\u6269\u5199|\u8865\u5145|\u5c55\u5f00)",
    flags=re.IGNORECASE,
)

_SUMMARIZE_RE = re.compile(r"(?:summarize|summary|\u603b\u7ed3|\u6982\u62ec|\u7f29\u5199)", re.IGNORECASE)
_EXPAND_RE = re.compile(r"(?:expand|elaborate|\u6269\u5199|\u5c55\u5f00|\u8865\u5145)", re.IGNORECASE)
_SIMPLIFY_RE = re.compile(r"(?:simplify|shorten|\u7b80\u5316|\u7cbe\u7b80)", re.IGNORECASE)
_IMPROVE_RE = re.compile(r"(?:improve|polish|optimize|\u6da6\u8272|\u4f18\u5316)", re.IGNORECASE)
_REPHRASE_RE = re.compile(r"(?:rewrite|rephrase|reword|\u91cd\u5199|\u6539\u5199)", re.IGNORECASE)


def _clean_instruction(raw: str) -> str:
    s = str(raw or "").strip()
    if not s:
        return ""
    return _POLITE_PREFIX_RE.sub("", s).strip()


def _classify_instruction(raw: str) -> Tuple[str, str]:
    s = _clean_instruction(raw)
    if not s:
        return "noop", ""
    if _DELETE_RE.search(s):
        return "delete", ""
    m = _REPLACE_RE.search(s)
    if m:
        content = str(m.group("content") or "").strip()
        if content:
            return "replace", content
    m = _PREPEND_RE.search(s)
    if m:
        content = str(m.group("content") or "").strip()
        if content:
            return "prepend", content
    m = _APPEND_RE.search(s)
    if m:
        content = str(m.group("content") or "").strip()
        if content:
            return "append", content
    if _REWRITE_RE.search(s):
        return "rewrite", ""
    return "rewrite", ""


_AI_RESULT_LABEL_RE = re.compile(
    r"(?im)^\s*(?:"
    r"\u6539\u5199\u540e(?:\u7684)?(?:\u6587\u672c|\u7248\u672c)?|"
    r"\u4f18\u5316\u540e(?:\u7684)?(?:\u6587\u672c|\u7248\u672c)?|"
    r"\u91cd\u5199\u540e(?:\u7684)?(?:\u6587\u672c|\u7248\u672c)?|"
    r"\u6da6\u8272\u540e(?:\u7684)?(?:\u6587\u672c|\u7248\u672c)?|"
    r"rewritten\\s*text|revised\\s*version|final\\s*version"
    r")\s*[:\uff1a]\s*"
)
_AI_META_LINE_RE = re.compile(
    r"(?im)^\s*(?:"
    r"\u539f\u6587|"
    r"\u6539\u5199\u8981\u6c42|"
    r"\u8bf4\u660e|"
    r"\u5907\u6ce8|"
    r"\u5904\u7406\u601d\u8def|"
    r"\u7ed3\u8bba|"
    r"original|instruction|note|analysis"
    r")\s*[:\uff1a].*$"
)


_AI_RESULT_LINE_RE = re.compile(
    r"(?im)^\s*(?:[-*]\s*)?(?:\d+[\.\)]\s*)?(?P<label>"
    r"\u6539\u5199\u540e(?:\u7684)?(?:\u6587\u672c|\u7248\u672c)?|"
    r"\u4f18\u5316\u540e(?:\u7684)?(?:\u6587\u672c|\u7248\u672c)?|"
    r"\u91cd\u5199\u540e(?:\u7684)?(?:\u6587\u672c|\u7248\u672c)?|"
    r"\u6da6\u8272\u540e(?:\u7684)?(?:\u6587\u672c|\u7248\u672c)?|"
    r"rewritten\\s*text|revised\\s*version|final\\s*version"
    r")\s*[:\uff1a]?\s*(?P<body>.*)$"
)
_AI_ORIGINAL_LINE_RE = re.compile(
    r"(?im)^\s*(?:[-*]\s*)?(?:\d+[\.\)]\s*)?(?:"
    r"\u539f\u6587|"
    r"original"
    r")\s*[:\uff1a]?\s*(?P<body>.*)$"
)


def _text_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _extract_result_segment(text: str) -> str:
    lines = [ln.rstrip() for ln in str(text or "").replace("\r", "\n").split("\n")]
    if not lines:
        return ""
    collecting = False
    chunks: list[str] = []
    for line in lines:
        m_res = _AI_RESULT_LINE_RE.match(line)
        if m_res:
            collecting = True
            body = (m_res.group("body") or "").strip()
            if body:
                chunks.append(body)
            continue
        if _AI_ORIGINAL_LINE_RE.match(line) or _AI_META_LINE_RE.match(line):
            collecting = False
            continue
        if collecting:
            chunks.append(line.strip())
    return "\n".join([x for x in chunks if x]).strip()


def _drop_original_chunks(text: str, original: str) -> str:
    s = str(text or "").strip()
    orig = str(original or "").strip()
    if not s or not orig:
        return s
    if s == orig:
        return s

    if s.startswith(orig):
        tail = s[len(orig):].lstrip(" \t\r\n:：-")
        if len(tail) >= 6:
            s = tail

    parts = [p.strip() for p in re.split(r"\n{2,}", s) if p.strip()]
    if len(parts) >= 2:
        keep = [p for p in parts if _text_similarity(p, orig) < 0.9]
        if keep and len(keep) < len(parts):
            s = "\n\n".join(keep).strip()

    line_parts = [ln.strip() for ln in s.splitlines() if ln.strip()]
    if len(line_parts) >= 2:
        keep_lines = [ln for ln in line_parts if _text_similarity(ln, orig) < 0.92]
        if keep_lines and len(keep_lines) < len(line_parts):
            s = "\n".join(keep_lines).strip()

    para_candidates = [p.strip() for p in re.split(r"\n{2,}", s) if p.strip()]
    if len(para_candidates) >= 2:
        ranked = sorted(
            para_candidates,
            key=lambda p: (_text_similarity(p, orig), -len(p)),
        )
        best = ranked[0]
        if _text_similarity(best, orig) < 0.9 and len(best) >= 6:
            s = best
    return s.strip()


def _clean_ai_rewrite_text(raw: str, original: str) -> str:
    s = str(raw or "").strip()
    if not s:
        return ""
    # Remove fenced wrappers.
    s = re.sub(r"^\s*```[a-zA-Z0-9_-]*\s*", "", s)
    s = re.sub(r"\s*```\s*$", "", s).strip()

    extracted = _extract_result_segment(s)
    if extracted:
        s = extracted

    # If model outputs "改写后的文本: ...", keep the tail after the last label.
    last_tail = None
    for m in _AI_RESULT_LABEL_RE.finditer(s):
        last_tail = s[m.end():].strip()
    if last_tail:
        s = last_tail

    # Drop obvious meta lines.
    s = _AI_META_LINE_RE.sub("", s).strip()

    # Remove common leading bullet prefixes.
    s = re.sub(r"(?im)^\s*(?:[-*]|\d+[\.\)])\s+", "", s).strip()

    s = _drop_original_chunks(s, original)

    return s.strip()


def _parse_list_items(text: str) -> Tuple[list[str], Optional[bool]]:
    if not text:
        return [], None
    lines = [ln.strip() for ln in str(text).splitlines() if ln.strip()]
    if not lines:
        return [], None
    items: list[str] = []
    ordered_hits = 0
    num_re = re.compile(r"^\d+[\.\)]\s+")
    bullet_re = re.compile(r"^[-\u2022\u00b7]\s+")
    for line in lines:
        if num_re.match(line):
            ordered_hits += 1
            items.append(num_re.sub("", line).strip())
            continue
        if bullet_re.match(line):
            items.append(bullet_re.sub("", line).strip())
            continue
        items.append(line)
    ordered = ordered_hits == len(lines)
    return items, ordered if ordered_hits > 0 else None


def _update_text_block(block, action: str, content: str) -> Dict[str, Any]:
    if isinstance(block, ParagraphBlock):
        current = str(block.text or "")
        if action == "append":
            new_text = (current.rstrip() + "\n" + content).strip()
        elif action == "prepend":
            new_text = (content + "\n" + current.lstrip()).strip()
        else:
            new_text = content.strip()
        return {"text": new_text}

    if isinstance(block, ListBlock):
        current_items = [str(x).strip() for x in (block.items or []) if str(x).strip()]
        new_items, ordered_hint = _parse_list_items(content)
        if action == "append":
            items = current_items + new_items
        elif action == "prepend":
            items = new_items + current_items
        else:
            items = new_items
        ordered = block.ordered
        if ordered_hint is not None:
            ordered = ordered_hint
        return {"items": items, "ordered": ordered}

    if isinstance(block, TableBlock):
        table = dict(block.table or {})
        caption = content.strip()
        if caption:
            table["caption"] = caption
        return {"table": table}

    if isinstance(block, FigureBlock):
        fig = dict(block.figure or {})
        caption = content.strip()
        if caption:
            fig["caption"] = caption
        return {"figure": fig}

    return {"text": content.strip()}


def _pick_inline_op(instruction: str) -> InlineOperation:
    s = str(instruction or "")
    if _SUMMARIZE_RE.search(s):
        return InlineOperation.SUMMARIZE
    if _EXPAND_RE.search(s):
        return InlineOperation.EXPAND
    if _SIMPLIFY_RE.search(s):
        return InlineOperation.SIMPLIFY
    if _IMPROVE_RE.search(s):
        return InlineOperation.IMPROVE
    if _REPHRASE_RE.search(s):
        return InlineOperation.REPHRASE
    return InlineOperation.REPHRASE


def _collect_block_context(doc: DocIR, block_id: str, window: int = 2) -> Tuple[str, str, str, Optional[str]]:
    idx = build_index(doc)
    block = idx.block_by_id.get(block_id)
    if block is None:
        return "", "", "", None
    sec_id = idx.block_parent_by_id.get(block_id)
    sec = idx.section_by_id.get(sec_id or "") if sec_id else None
    blocks = sec.blocks if sec else []
    texts = [render_block_text(b).strip() for b in blocks]
    pos = 0
    for i, b in enumerate(blocks):
        if getattr(b, "id", "") == block_id:
            pos = i
            break
    before = "\n".join([t for t in texts[max(0, pos - window):pos] if t])
    after = "\n".join([t for t in texts[pos + 1:pos + 1 + window] if t])
    selected = render_block_text(block).strip()
    section_title = sec.title if sec else None
    return selected, before, after, section_title


async def apply_block_edit(doc: DocIR, block_id: str, instruction: str) -> Tuple[DocIR, Dict[str, Any]]:
    meta: Dict[str, Any] = {"action": None}
    if not block_id:
        return doc, meta
    idx = build_index(doc)
    block = idx.block_by_id.get(block_id)
    if block is None:
        return doc, meta

    action, content = _classify_instruction(instruction)
    meta["action"] = action

    if action == "noop":
        return doc, meta

    if action == "delete":
        ops = [Operation(op="delete", target_id=block_id)]
        return apply_ops(doc, ops, atomic=True), meta

    if action in {"replace", "append", "prepend"}:
        payload = _update_text_block(block, action, content)
        ops = [Operation(op="update", target_id=block_id, payload=payload)]
        return apply_ops(doc, ops, atomic=True), meta

    # rewrite path (inline AI)
    selected, before, after, section_title = _collect_block_context(doc, block_id)
    if not selected:
        return doc, meta

    op = _pick_inline_op(instruction)
    meta["ai_op"] = op.value
    engine = InlineAIEngine()
    context = InlineContext(
        selected_text=selected,
        before_text=before,
        after_text=after,
        document_title=doc.title or "",
        section_title=section_title,
    )
    result = await engine.execute_operation(op, context)
    if not result.success or not result.generated_text:
        return doc, meta

    cleaned = _clean_ai_rewrite_text(result.generated_text, selected)
    if not cleaned:
        return doc, meta
    payload = _update_text_block(block, "replace", cleaned)
    ops = [Operation(op="update", target_id=block_id, payload=payload)]
    return apply_ops(doc, ops, atomic=True), meta
