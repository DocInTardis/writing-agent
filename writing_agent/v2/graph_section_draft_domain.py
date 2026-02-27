"""Graph Section Draft Domain module.

This module belongs to `writing_agent.v2` in the writing-agent codebase.
"""

from __future__ import annotations

import json
import os
import queue
import re
import time
from typing import Callable


REF_HEADING_RE = re.compile(r"^\s*(参考文献|references|bibliography)\s*$", re.IGNORECASE)
REF_LINE_RE = re.compile(r"^\s*\[\d+\]\s+")


def strip_reference_like_lines(text: str) -> str:
    if not text:
        return ""
    lines = (text or "").splitlines()
    out: list[str] = []
    drop_rest = False
    for line in lines:
        token = (line or "").strip()
        if REF_HEADING_RE.match(token):
            drop_rest = True
            continue
        if drop_rest:
            continue
        if REF_LINE_RE.match(token):
            continue
        out.append(line)
    return "\n".join(out).strip()


def normalize_section_id(section: str, *, section_token_re: re.Pattern[str], encode_section: Callable[[int, str], str]) -> str:
    value = (section or "").strip()
    if value and section_token_re.match(value):
        return value
    return encode_section(2, value or "section")


def parse_structured_payload(payload) -> list[dict]:
    if isinstance(payload, dict):
        if isinstance(payload.get("blocks"), list):
            return [b for b in payload.get("blocks") if isinstance(b, dict)]
        if any(k in payload for k in ("text", "items", "type", "block_id", "id")):
            return [payload]
    if isinstance(payload, list):
        return [b for b in payload if isinstance(b, dict)]
    return []


def parse_structured_line(line: str) -> list[dict]:
    value = (line or "").strip()
    if not value or value.startswith("```"):
        return []
    try:
        payload = json.loads(value)
    except Exception:
        return []
    return parse_structured_payload(payload)


def render_block_to_text(block: dict) -> str:
    block_type = str(block.get("type") or "paragraph").lower()
    if block_type in {"paragraph", "text", "p"}:
        return str(block.get("text") or "").strip()
    if block_type in {"list", "bullets", "bullet"}:
        items = block.get("items")
        if isinstance(items, list):
            return "\n".join([f"- {str(i).strip()}" for i in items if str(i).strip()]).strip()
        raw = str(block.get("text") or "").strip()
        if raw:
            lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
            return "\n".join([ln if ln.startswith("-") else f"- {ln}" for ln in lines]).strip()
        return ""
    if block_type in {"table", "figure"}:
        marker = "TABLE" if block_type == "table" else "FIGURE"
        payload = {}
        for key in ("caption", "columns", "rows", "data"):
            if key in block and block.get(key) is not None:
                payload[key] = block.get(key)
        return f"[[{marker}:{json.dumps(payload, ensure_ascii=False)}]]"
    if block_type in {"reference", "ref"}:
        raw = str(block.get("text") or "").strip()
        if raw:
            return raw
        items = block.get("items")
        if isinstance(items, list):
            return "\n".join([str(i).strip() for i in items if str(i).strip()]).strip()
        return ""
    return str(block.get("text") or "").strip()


def persist_block_to_store(block: dict, text_store) -> str | None:
    if text_store is None or not isinstance(block, dict):
        return None
    block_type = str(block.get("type") or "paragraph").lower()
    block_id = str(block.get("block_id") or block.get("id") or "").strip() or None
    if block_type in {"paragraph", "text", "p"}:
        text = str(block.get("text") or "").strip()
        if not text:
            return block_id
        return text_store.put_text(text, block_id=block_id)
    if block_type in {"list", "bullets", "bullet"}:
        items = block.get("items")
        payload = {"items": items} if isinstance(items, list) else {"text": str(block.get("text") or "").strip()}
        return text_store.put_json(payload, block_id=block_id, prefix="l")
    if block_type == "table":
        payload = {}
        for key in ("caption", "columns", "rows", "data"):
            if key in block and block.get(key) is not None:
                payload[key] = block.get(key)
        return text_store.put_json(payload, block_id=block_id, prefix="t")
    if block_type == "figure":
        payload = {}
        for key in ("caption", "data"):
            if key in block and block.get(key) is not None:
                payload[key] = block.get(key)
        return text_store.put_json(payload, block_id=block_id, prefix="f")
    if block_type in {"reference", "ref"}:
        text = str(block.get("text") or "").strip()
        if not text:
            items = block.get("items")
            if isinstance(items, list):
                text = "\n".join([str(i).strip() for i in items if str(i).strip()]).strip()
        if not text:
            return block_id
        return text_store.put_text(text, block_id=block_id)
    return block_id


def accept_block(block: dict, section_id: str, is_reference: bool) -> bool:
    sec = str(block.get("section_id") or "").strip()
    if sec and sec != section_id:
        return False
    block_type = str(block.get("type") or "").lower()
    if not is_reference and block_type in {"reference", "ref"}:
        return False
    return True


def stream_structured_blocks(
    *,
    client,
    system: str,
    user: str,
    out_queue: queue.Queue[dict],
    section: str,
    section_id: str,
    is_reference: bool,
    num_predict: int,
    deadline: float,
    strict_json: bool = True,
    text_store=None,
) -> str:
    strict_json_raw = os.environ.get("WRITING_AGENT_STRICT_JSON", "0").strip().lower()
    strict_json_env = strict_json_raw in {"1", "true", "yes", "on"}
    strict_json = bool(strict_json) and strict_json_env
    buf = ""
    texts: list[str] = []
    seen: set[str] = set()
    invalid_line = False
    for delta in client.chat_stream(system=system, user=user, temperature=0.35, options={"num_predict": num_predict}):
        if time.time() > deadline:
            break
        buf += delta
        while "\n" in buf:
            line, buf = buf.split("\n", 1)
            parsed = parse_structured_line(line)
            if not parsed and line.strip():
                invalid_line = True
            for block in parsed:
                if not accept_block(block, section_id, is_reference):
                    continue
                stored_id = persist_block_to_store(block, text_store)
                text = render_block_to_text(block)
                if not text:
                    continue
                block_id = str(stored_id or block.get("block_id") or block.get("id") or f"b{len(seen) + 1}")
                if block_id in seen:
                    continue
                seen.add(block_id)
                texts.append(text)
                block_type = str(block.get("type") or "paragraph")
                payload = {
                    "event": "section",
                    "phase": "delta",
                    "section": section,
                    "delta": text,
                    "block_id": block_id,
                    "block_type": block_type,
                }
                if block_type in {"paragraph", "text", "p", "list", "bullets", "bullet", "reference", "ref"}:
                    payload.pop("block_id", None)
                out_queue.put(payload)
    leftover = buf.strip()
    if leftover:
        try:
            payload = json.loads(leftover)
            blocks = parse_structured_payload(payload)
        except Exception:
            blocks = []
            if leftover.strip():
                invalid_line = True
        for block in blocks:
            if not accept_block(block, section_id, is_reference):
                continue
            stored_id = persist_block_to_store(block, text_store)
            text = render_block_to_text(block)
            if not text:
                continue
            block_id = str(stored_id or block.get("block_id") or block.get("id") or f"b{len(seen) + 1}")
            if block_id in seen:
                continue
            seen.add(block_id)
            texts.append(text)
            block_type = str(block.get("type") or "paragraph")
            payload = {
                "event": "section",
                "phase": "delta",
                "section": section,
                "delta": text,
                "block_id": block_id,
                "block_type": block_type,
            }
            if block_type in {"paragraph", "text", "p", "list", "bullets", "bullet", "reference", "ref"}:
                payload.pop("block_id", None)
            out_queue.put(payload)
        if strict_json and invalid_line and not texts:
            raise ValueError("writer output contains non-json lines")
    if strict_json and not texts:
        raise ValueError("writer output has no valid blocks")
    return "\n\n".join([t for t in texts if t]).strip()


def strip_inline_headings(
    text: str,
    section_title: str,
    *,
    looks_like_heading_text: Callable[[str], bool],
) -> str:
    lines = []
    for line in (text or "").splitlines():
        token = line.strip()
        if not token:
            lines.append("")
            continue
        if re.match(r"^#{1,6}$", token):
            continue
        is_heading = False
        if re.match(r"^\s*#{1,6}\s+", token):
            is_heading = True
            token = re.sub(r"^\s*#{1,6}\s+", "", token).strip()
        if re.match(r"^第\s*\d+\s*[章节]\s*", token):
            is_heading = True
            token = re.sub(r"^第\s*\d+\s*[章节]\s*", "", token).strip()
        if section_title and token == section_title:
            continue
        if re.match(r"^[一二三四五六七八九十]+[、.]\s*", token):
            is_heading = True
            token = re.sub(r"^[一二三四五六七八九十]+[、.]\s*", "", token).strip()
        if re.match(r"^\d+(?:\.\d+)*\s+", token):
            is_heading = True
            token = re.sub(r"^\d+(?:\.\d+)*\s+", "", token).strip()
        if not token:
            continue
        if is_heading:
            continue
        if len(token) <= 10 and not re.search(r"[。！？；：]", token) and looks_like_heading_text(token):
            continue
        lines.append(token)
    return "\n".join(lines).strip()


def format_references(text: str, *, strip_markdown_noise: Callable[[str], str]) -> str:
    raw = (text or "").replace("\r", "")
    raw = strip_markdown_noise(raw)
    lines = []
    for line in raw.splitlines():
        token = line.strip()
        if not token:
            continue
        if "引用格式" in token or "格式示例" in token:
            continue
        token = re.sub(r"^\s*[-*\u2022]\s+", "", token)
        token = re.sub(r"^\s*\d+\.\s*", "", token)
        token = re.sub(r"^\s*\[(?:\d+)\]\s*", "", token)
        token = token.strip()
        if token:
            lines.append(token)

    if not lines:
        return ""
    merged: list[str] = []
    for line in lines:
        if merged and (len(line) <= 8 or re.fullmatch(r"[\d\W]+", line)):
            merged[-1] = (merged[-1].rstrip("，,") + " " + line).strip()
        else:
            merged.append(line)
    out: list[str] = []
    for i, line in enumerate(merged, 1):
        out.append(f"[{i}] {line}")
    return "\n\n".join(out)


def ensure_media_markers(
    text: str,
    *,
    section_title: str,
    min_tables: int,
    min_figures: int,
    is_reference_section: Callable[[str], bool],
) -> str:
    if not text:
        return text
    if is_reference_section(section_title):
        return text
    _ = len(re.findall(r"\[\[\s*TABLE\s*:\s*\{[\s\S]*?\}\s*\]\]", text, flags=re.IGNORECASE))
    _ = len(re.findall(r"\[\[\s*FIGURE\s*:\s*\{[\s\S]*?\}\s*\]\]", text, flags=re.IGNORECASE))
    append_lines: list[str] = []
    if not append_lines:
        return text
    return (text.strip() + "\n\n" + "\n\n".join(append_lines)).strip()


def generic_fill_paragraph(
    section: str,
    *,
    idx: int = 1,
    section_title: Callable[[str], str],
    is_reference_section: Callable[[str], bool],
    find_section_description: Callable[[str], str],
) -> str:
    sec = (section_title(section) or "").strip() or "本节"
    if is_reference_section(sec):
        return ""

    desc = find_section_description(sec)
    if desc:
        templates = [
            f"{desc}. This section should define scope, constraints, and expected deliverables.",
            f"For {sec}, describe key workflow, inputs/outputs, and acceptance criteria in a verifiable way.",
            f"For {sec}, explain assumptions, implementation path, and risk controls to ensure execution quality.",
            f"For {sec}, clarify terminology, boundaries, and measurable outcomes for downstream sections.",
        ]
        return templates[(idx - 1) % len(templates)]

    defaults = [
        f"{sec} should cover objective, scope, constraints, and expected outputs with concrete checks.",
        "Describe workflow, roles, data interfaces, and validation criteria for key steps.",
        "Highlight implementation strategy, edge cases, and risk mitigation to ensure operability.",
        "Provide measurable acceptance rules and clarify assumptions and limitations.",
    ]
    return defaults[(idx - 1) % len(defaults)]


def fast_fill_references(topic: str) -> str:
    return ""


def fast_fill_section(
    section: str,
    *,
    min_paras: int,
    min_chars: int,
    min_tables: int,
    min_figures: int,
    section_title: Callable[[str], str],
    is_reference_section: Callable[[str], bool],
    generic_fill_paragraph: Callable[[str, int], str],
) -> str:
    sec_title = (section_title(section) or "").strip()
    if is_reference_section(sec_title):
        return fast_fill_references(sec_title)
    paras: list[str] = []
    target_paras = max(2, min_paras)
    while len(paras) < target_paras:
        paras.append(generic_fill_paragraph(section, len(paras) + 1))
    body = "\n\n".join(paras)
    body_len = len(re.sub(r"\s+", "", body))
    while body_len < min_chars:
        paras.append(generic_fill_paragraph(section, len(paras) + 1))
        body = "\n\n".join(paras)
        body_len = len(re.sub(r"\s+", "", body))
        if len(paras) >= target_paras + 6:
            break
    extras: list[str] = []
    if min_tables > 0:
        extras.append('[[TABLE:{"caption":"关键指标与功能对比","columns":["指标","说明","备注"],"rows":[["准确性","满足业务核算需求",""],["效率","减少人工核对",""],["可维护性","结构清晰易扩展",""]]}]]')
    if min_figures > 0:
        extras.append('[[FIGURE:{"type":"flow","caption":"业务流程示意","data":{"nodes":["录入","核算","审批","发放"],"edges":[["录入","核算"],["核算","审批"],["审批","发放"]]}}]]')
    if extras:
        body = body.strip() + "\n\n" + "\n\n".join(extras)
    return body.strip()


def postprocess_section(
    section: str,
    txt: str,
    *,
    min_paras: int,
    min_chars: int,
    max_chars: int,
    min_tables: int,
    min_figures: int,
    section_title: Callable[[str], str],
    is_reference_section: Callable[[str], bool],
    format_references: Callable[[str], str],
    strip_reference_like_lines: Callable[[str], str],
    strip_inline_headings: Callable[[str, str], str],
    generic_fill_paragraph: Callable[[str, int], str],
    sanitize_output_text: Callable[[str], str],
    ensure_media_markers: Callable[[str, str, int, int], str],
) -> str:
    value = (txt or "").replace("\r", "").strip()
    sec_title = (section_title(section) or "").strip()
    if is_reference_section(sec_title):
        value = format_references(value)
    else:
        value = strip_reference_like_lines(value)
        value = strip_inline_headings(value, sec_title)
    bullet_re = re.compile(r"^\s*[\u2022\u00B7]\s+")
    lines = [ln.strip() for ln in value.splitlines()]
    has_bullets = any(bullet_re.match(ln) for ln in lines if ln)
    if has_bullets:
        paras: list[str] = []
        buf: list[str] = []
        for line in lines:
            if not line:
                if buf:
                    paras.append(" ".join(buf).strip())
                    buf = []
                continue
            if bullet_re.match(line):
                if buf:
                    paras.append(" ".join(buf).strip())
                    buf = []
                paras.append(line.strip())
                continue
            buf.append(line)
        if buf:
            paras.append(" ".join(buf).strip())
    else:
        paras = [p.strip() for p in re.split(r"\n\s*\n+", value) if p.strip()]
        paras = [re.sub(r"\s*\n+\s*", " ", p).strip() for p in paras if p.strip()]
    if len(paras) <= 1 and len(value) >= 420:
        parts = [p.strip() for p in re.split(r"(?<=[。！？!?\.])\s*", " ".join(paras) or value) if p.strip()]
        if len(parts) >= 6:
            chunked: list[str] = []
            buf: list[str] = []
            for part in parts:
                buf.append(part)
                if len("".join(buf)) >= 180:
                    chunked.append("".join(buf).strip())
                    buf = []
            if buf:
                chunked.append("".join(buf).strip())
            paras = [p for p in chunked if p]
    content_len = len(re.sub(r"\[\[(?:FIGURE|TABLE)\s*:\s*\{[\s\S]*?\}\s*\]\]", "", value).strip())
    if len(paras) < max(2, min_paras) and content_len < 260:
        need = max(2, min_paras) - len(paras)
        for i in range(need):
            paras.append(generic_fill_paragraph(section, i + 1))

    joined = "\n\n".join(paras)
    if min_chars > 0:
        body_len = len(re.sub(r"\[\[(?:FIGURE|TABLE)\s*:\s*\{[\s\S]*?\}\s*\]\]", "", joined).strip())
        if body_len < max(220, int(min_chars * 0.6)):
            extra_rounds = 0
            while body_len < min_chars and extra_rounds < 3:
                paras.append(generic_fill_paragraph(section, len(paras) + 1))
                joined = "\n\n".join(paras)
                body_len = len(re.sub(r"\[\[(?:FIGURE|TABLE)\s*:\s*\{[\s\S]*?\}\s*\]\]", "", joined).strip())
                extra_rounds += 1
    if max_chars > 0:
        hard_max_mode = os.environ.get("WRITING_AGENT_HARD_MAX", "0").strip() in {"1", "true", "yes"}
        if hard_max_mode:
            body_len = len(re.sub(r"\[\[(?:FIGURE|TABLE)\s*:\s*\{[\s\S]*?\}\s*\]\]", "", joined).strip())
            if body_len > max_chars:
                trimmed: list[str] = []
                cur = 0
                for para in paras:
                    next_len = len(re.sub(r"\[\[(?:FIGURE|TABLE)\s*:\s*\{[\s\S]*?\}\s*\]\]", "", para).strip())
                    if cur + next_len <= max_chars or not trimmed:
                        trimmed.append(para)
                        cur += next_len
                    else:
                        break
                joined = "\n\n".join(trimmed)
                body_len = len(re.sub(r"\[\[(?:FIGURE|TABLE)\s*:\s*\{[\s\S]*?\}\s*\]\]", "", joined).strip())
                if body_len > max_chars:
                    joined = joined[:max_chars].rsplit("\n", 1)[0].strip()
    joined = sanitize_output_text(joined).strip()
    joined = ensure_media_markers(joined, sec_title, min_tables, min_figures)
    return joined.strip()


def _section_body_len(text: str) -> int:
    return len(re.sub(r"\[\[(?:FIGURE|TABLE)\s*:\s*\{[\s\S]*?\}\s*\]\]", "", str(text or "")).strip())


def _section_paragraphs(text: str) -> list[str]:
    return [p for p in re.split(r"\n\s*\n+", str(text or "")) if p.strip()]


def _section_minimum_satisfied(*, text: str, min_paras: int, min_chars: int) -> bool:
    paras = _section_paragraphs(text)
    body_len = _section_body_len(text)
    return (len(paras) >= min_paras) and (min_chars <= 0 or body_len >= min_chars)


def _build_continue_prompt(
    *,
    title: str,
    section: str,
    parent_section: str,
    instruction: str,
    analysis_summary: str,
    evidence_summary: str,
    allowed_urls: list[str],
    plan_hint: str,
    txt: str,
    section_id: str,
    min_paras: int,
    missing_chars: int,
) -> tuple[str, str]:
    system = (
        "You are a continuation writer for one section.\n"
        "Output NDJSON only. Each line is a JSON object with paragraph/list/table/figure/reference blocks.\n"
        "Do not repeat prior content; only add incremental blocks that extend the section.\n"
    )
    if evidence_summary:
        system += "Use only evidence provided and avoid unsupported URLs.\n"
    user = f"title: {title}\nsection: {section}\nsection_id: {section_id}\n"
    if parent_section:
        user += f"parent_section: {parent_section}\n"
    if analysis_summary:
        user += f"\nanalysis summary:\n{analysis_summary}\n\n"
    else:
        user += f"\nuser instruction:\n{instruction}\n\n"
    if plan_hint:
        user += f"plan hint:\n{plan_hint}\n\n"
    if evidence_summary:
        user += f"evidence summary:\n{evidence_summary}\n\n"
    if allowed_urls:
        user += "allowed urls:\n" + "\n".join([f"- {u}" for u in allowed_urls]) + "\n\n"
    user += f"current section draft:\n{txt}\n\n"
    user += f"Please continue and add at least {max(220, missing_chars)} chars to satisfy minimum {min_paras} paragraphs."
    return system, user


def _continue_once(
    *,
    client,
    txt: str,
    section: str,
    section_id: str,
    system: str,
    user: str,
    out_queue: queue.Queue[dict],
    max_chars: int,
    missing_chars: int,
    stream_structured_blocks: Callable[..., str],
    predict_num_tokens: Callable[[int, int, bool], int],
    is_reference_section: Callable[[str], bool],
    section_timeout_s: Callable[[], float],
) -> str:
    deadline = time.time() + section_timeout_s()
    extra = stream_structured_blocks(
        client=client,
        system=system,
        user=user,
        out_queue=out_queue,
        section=section,
        section_id=section_id,
        is_reference=is_reference_section(section),
        num_predict=predict_num_tokens(max(220, missing_chars), max_chars, is_reference_section(section)),
        deadline=deadline,
    )
    if not extra:
        return txt
    return (str(txt or "").strip() + "\n\n" + extra).strip()


def ensure_section_minimums_stream(
    *,
    base_url: str,
    model: str,
    title: str,
    section: str,
    parent_section: str,
    instruction: str,
    analysis_summary: str,
    evidence_summary: str,
    allowed_urls: list[str],
    plan_hint: str,
    draft: str,
    min_paras: int,
    min_chars: int,
    max_chars: int,
    min_tables: int,
    min_figures: int,
    out_queue: queue.Queue[dict],
    postprocess_section: Callable[..., str],
    stream_structured_blocks: Callable[..., str],
    normalize_section_id: Callable[[str], str],
    predict_num_tokens: Callable[[int, int, bool], int],
    is_reference_section: Callable[[str], bool],
    section_timeout_s: Callable[[], float],
    ollama_client_cls,
) -> str:
    txt = postprocess_section(
        section,
        draft,
        min_paras=min_paras,
        min_chars=min_chars,
        max_chars=max_chars,
        min_tables=min_tables,
        min_figures=min_figures,
    )
    if _section_minimum_satisfied(text=txt, min_paras=min_paras, min_chars=min_chars):
        return txt

    rounds = max(0, min(2, int(os.environ.get("WRITING_AGENT_SECTION_CONTINUE_ROUNDS", "2"))))
    if rounds <= 0:
        return txt

    client = ollama_client_cls(base_url=base_url, model=model, timeout_s=240.0)
    section_id = normalize_section_id(section)
    for attempt in range(1, rounds + 1):
        body_len = _section_body_len(txt)
        missing_chars = max(0, int(min_chars) - body_len) if min_chars > 0 else 0
        system, user = _build_continue_prompt(
            title=title,
            section=section,
            parent_section=parent_section,
            instruction=instruction,
            analysis_summary=analysis_summary,
            evidence_summary=evidence_summary,
            allowed_urls=allowed_urls,
            plan_hint=plan_hint,
            txt=txt,
            section_id=section_id,
            min_paras=min_paras,
            missing_chars=missing_chars,
        )
        txt = _continue_once(
            client=client,
            txt=txt,
            section=section,
            section_id=section_id,
            system=system,
            user=user,
            out_queue=out_queue,
            max_chars=max_chars,
            missing_chars=missing_chars,
            stream_structured_blocks=stream_structured_blocks,
            predict_num_tokens=predict_num_tokens,
            is_reference_section=is_reference_section,
            section_timeout_s=section_timeout_s,
        )
        txt = postprocess_section(
            section,
            txt,
            min_paras=min_paras,
            min_chars=min_chars,
            max_chars=max_chars,
            min_tables=min_tables,
            min_figures=min_figures,
        )
        if _section_minimum_satisfied(text=txt, min_paras=min_paras, min_chars=min_chars):
            break
        body_len = _section_body_len(txt)
        if attempt >= rounds and body_len > 0 and body_len < min_chars:
            retry_missing = min_chars - body_len
            if retry_missing > 100:
                out_queue.put(
                    {
                        "event": "section",
                        "phase": "retry",
                        "section": section,
                        "message": f"content below target ({body_len}/{min_chars}), continuing...",
                    }
                )
                retry_user = f"{user}\n\nCurrent content:\n{txt}\n\nPlease continue and add around {retry_missing} more characters."
                txt = _continue_once(
                    client=client,
                    txt=txt,
                    section=section,
                    section_id=section_id,
                    system=system,
                    user=retry_user,
                    out_queue=out_queue,
                    max_chars=max_chars,
                    missing_chars=retry_missing,
                    stream_structured_blocks=stream_structured_blocks,
                    predict_num_tokens=predict_num_tokens,
                    is_reference_section=is_reference_section,
                    section_timeout_s=section_timeout_s,
                )
                if _section_body_len(txt) >= min_chars:
                    break
    return txt
