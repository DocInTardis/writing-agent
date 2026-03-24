import os
import queue
import re

import pytest

from writing_agent.document import v2_report_docx_helpers as docx_helpers
from writing_agent.v2 import graph_section_draft_domain as section_domain
from writing_agent.v2 import graph_text_sanitize_domain as sanitize_domain
from writing_agent.web import app_v2_textops_runtime_part2 as textops_part2
from writing_agent.web.domains import section_edit_ops_domain
from writing_agent.web.api.editing_flow import _normalize_inline_context_policy, _trim_inline_context


def test_inline_context_meta_contains_reason_codes() -> None:
    policy = _normalize_inline_context_policy({"context_total_max_chars": 600})
    before_trim, after_trim, meta = _trim_inline_context(
        selected_text="x" * 2000,
        before_text="A" * 3000,
        after_text="B" * 3000,
        policy=policy,
    )
    assert before_trim and after_trim
    assert meta["trimmed_for_budget"] is True
    reasons = set(meta.get("truncate_reason_codes") or [])
    assert "context_window" in reasons
    assert "context_total_cap" in reasons


def test_reference_extract_conservative_mode_keeps_compound_item(monkeypatch) -> None:
    monkeypatch.setenv("WRITING_AGENT_REFERENCE_CONSERVATIVE_REPAIR", "1")
    textops_part2.bind({"re": re, "os": os, "section_edit_ops_domain": section_edit_ops_domain})
    text = """
## 参考文献

[1] 1. Alpha A. 2022. URL: https://a.example 2. Beta B. 2023. URL: https://b.example
""".strip()
    items = textops_part2._extract_reference_items_from_text(text)
    assert len(items) == 1
    assert "Alpha A" in items[0]
    assert "Beta B" in items[0]


def test_docx_heading_tail_split_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("WRITING_AGENT_DOCX_AGGRESSIVE_SPLIT", raising=False)
    src = "这是一个很长的标题并且后面还有一句完整的解释性正文内容"
    head, tail = docx_helpers._split_heading_tail(src)
    assert head == src
    assert tail == ""


def test_sanitize_output_keeps_ascii_lines_by_default(monkeypatch) -> None:
    monkeypatch.delenv("WRITING_AGENT_DROP_ASCII_LINES", raising=False)
    src = "RFC 6902 JSON Patch\n中文段落"
    out = sanitize_domain.sanitize_output_text(
        src,
        meta_phrases=[],
        has_cjk=lambda s: bool(any("\u4e00" <= ch <= "\u9fff" for ch in str(s))),
        is_mostly_ascii_line=lambda s: s.isascii() and any(ch.isalpha() for ch in s),
        banned_phrases=[],
    )
    assert "RFC 6902" in out
    assert "中文段落" in out


class _DummyClient:
    def chat_stream(self, **_kwargs):
        yield "this-is-not-json\n"


def test_stream_structured_blocks_strict_json_on_by_default(monkeypatch) -> None:
    monkeypatch.delenv("WRITING_AGENT_STRICT_JSON", raising=False)
    q = queue.Queue()
    out = section_domain.stream_structured_blocks(
        client=_DummyClient(),
        system="s",
        user="u",
        out_queue=q,
        section="H2::测试",
        section_id="H2::测试",
        is_reference=False,
        num_predict=128,
        deadline=10**12,
        strict_json=True,
        text_store=None,
    )
    assert "this-is-not-json" in out
    events = []
    while not q.empty():
        events.append(q.get_nowait())
    assert any(str(ev.get("fallback_mode") or "") == "plain_text_recovery" for ev in events)
