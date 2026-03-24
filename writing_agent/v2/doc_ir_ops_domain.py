"""Diff, index, and operation helpers for doc IR."""

from __future__ import annotations

from typing import Dict, List, Tuple


def _base():
    from writing_agent.v2 import doc_ir as base
    return base


def myers_diff(a: List[str], b: List[str]) -> List[Tuple[str, int, int]]:
    n, m = len(a), len(b)
    max_d = n + m
    v = {1: 0}
    trace = []
    for d in range(max_d + 1):
        v2 = {}
        for k in range(-d, d + 1, 2):
            if k == -d or (k != d and v.get(k - 1, 0) < v.get(k + 1, 0)):
                x = v.get(k + 1, 0)
            else:
                x = v.get(k - 1, 0) + 1
            y = x - k
            while x < n and y < m and a[x] == b[y]:
                x += 1
                y += 1
            v2[k] = x
            if x >= n and y >= m:
                trace.append(v2)
                return _backtrack(trace, a, b)
        trace.append(v2)
        v = v2
    return []


def _backtrack(trace: List[Dict[int, int]], a: List[str], b: List[str]) -> List[Tuple[str, int, int]]:
    x = len(a)
    y = len(b)
    edits: List[Tuple[str, int, int]] = []
    for d in range(len(trace) - 1, -1, -1):
        v = trace[d]
        k = x - y
        if d == 0:
            break
        if k == -d or (k != d and v.get(k - 1, 0) < v.get(k + 1, 0)):
            k_prev = k + 1
            x_prev = v.get(k_prev, 0)
            op = "insert"
        else:
            k_prev = k - 1
            x_prev = v.get(k_prev, 0) + 1
            op = "delete"
        y_prev = x_prev - k_prev
        while x > x_prev and y > y_prev:
            edits.append(("equal", x - 1, y - 1))
            x -= 1
            y -= 1
        edits.append((op, x_prev, y_prev))
        x, y = x_prev, y_prev
    edits.reverse()
    return edits


def diff_blocks(old, new) -> List[Tuple[str, int, int]]:
    base = _base()
    old_hashes = [block.content_hash() for block in base.iter_blocks(old)]
    new_hashes = [block.content_hash() for block in base.iter_blocks(new)]
    return myers_diff(old_hashes, new_hashes)


def build_inverted_index(doc) -> Dict[str, List[str]]:
    base = _base()
    index: Dict[str, List[str]] = {}
    for block in base.iter_blocks(doc):
        text = base.render_block_text(block).strip()
        if not text:
            continue
        for token in base._WORD_RE.findall(text):
            token = token.lower()
            index.setdefault(token, []).append(base.get_block_id(block))
    return index


def validate_doc_ir(doc) -> List[str]:
    problems: List[str] = []
    if not doc.title or not doc.title.strip():
        problems.append("missing title")
    if not doc.sections:
        problems.append("missing sections")
    return problems


def apply_ops(doc, ops, *, atomic: bool = False):
    base = _base()
    target = doc.model_copy(deep=True) if atomic else doc
    if not ops:
        return target
    idx = base.build_index(target)
    for op in ops:
        if not _apply_single_op(target, idx, op):
            if atomic:
                return doc
            continue
    return target


def _delete_block_in_section(sec, block_id: str) -> bool:
    base = _base()
    for i, block in enumerate(sec.blocks):
        if base.get_block_id(block) == block_id:
            sec.blocks.pop(i)
            return True
    for child in sec.children:
        if _delete_block_in_section(child, block_id):
            return True
    return False


def _apply_single_op(doc, idx, op) -> bool:
    base = _base()
    if op.op == "insert":
        sec = idx.section_by_id.get(op.parent_id or "")
        if not sec:
            return False
        block = base.block_from_dict(op.payload or {})
        pos = int(op.index or len(sec.blocks))
        sec.blocks.insert(max(0, min(len(sec.blocks), pos)), block)
        bid = base.get_block_id(block)
        if bid:
            idx.block_by_id[bid] = block
            idx.block_parent_by_id[bid] = sec.id
        return True
    if op.op == "delete":
        sec_id = idx.block_parent_by_id.get(op.target_id)
        if not sec_id:
            return False
        sec = idx.section_by_id.get(sec_id)
        if not sec:
            return False
        for i, block in enumerate(sec.blocks):
            if base.get_block_id(block) == op.target_id:
                sec.blocks.pop(i)
                idx.block_by_id.pop(op.target_id, None)
                idx.block_parent_by_id.pop(op.target_id, None)
                return True
        return False
    if op.op == "update":
        block = idx.block_by_id.get(op.target_id)
        if not block or not op.payload:
            return False
        for key, value in op.payload.items():
            if hasattr(block, key):
                setattr(block, key, value)
        return True
    if op.op == "move":
        sec_id = idx.block_parent_by_id.get(op.target_id)
        if not sec_id:
            return False
        src_sec = idx.section_by_id.get(sec_id)
        if not src_sec:
            return False
        moving = None
        for i, block in enumerate(src_sec.blocks):
            if base.get_block_id(block) == op.target_id:
                moving = src_sec.blocks.pop(i)
                break
        if moving is None:
            return False
        dst_id = op.parent_id or sec_id
        dst_sec = idx.section_by_id.get(dst_id)
        if not dst_sec:
            return False
        pos = int(op.index or len(dst_sec.blocks))
        dst_sec.blocks.insert(max(0, min(len(dst_sec.blocks), pos)), moving)
        idx.block_parent_by_id[op.target_id] = dst_sec.id
        return True
    return False


__all__ = [name for name in globals() if not name.startswith("__")]
