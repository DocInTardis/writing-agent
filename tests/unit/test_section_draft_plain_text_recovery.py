from __future__ import annotations

import queue
import time

from writing_agent.v2 import graph_section_draft_domain as draft_domain


class _PlainTextClient:
    def chat_stream(self, **_kwargs):
        yield "这是一段普通文本，不是 JSON。\n"
        yield "第二段普通文本。\n"


class _MultilineJsonClient:
    def chat_stream(self, **_kwargs):
        yield "{\n"
        yield '  "section_id": "H2::引言",\n'
        yield '  "type": "paragraph",\n'
        yield '  "text": "这是通过多行 JSON 返回的段落内容。"\n'
        yield "}\n"


class _JsonResidueClient:
    def chat_stream(self, **_kwargs):
        yield '"section_id":"H2::引言","block_id":"1","type":"paragraph","text":"这是可保存的正文内容。"\n'
        yield '"section_id":"H2::引言","block_id":"2","type":"table","caption":"这条应被过滤"\n'


def test_stream_structured_blocks_recovers_plain_text_when_strict_json_enabled():
    q: queue.Queue[dict] = queue.Queue()
    text = draft_domain.stream_structured_blocks(
        client=_PlainTextClient(),
        system="system",
        user="user",
        out_queue=q,
        section="引言",
        section_id="H2::引言",
        is_reference=False,
        num_predict=512,
        deadline=time.time() + 10.0,
        strict_json=True,
        text_store=None,
    )
    assert "普通文本" in text
    deltas = []
    while not q.empty():
        deltas.append(q.get_nowait())
    assert any(str(d.get("fallback_mode") or "") == "plain_text_recovery" for d in deltas)


def test_stream_structured_blocks_recovers_multiline_json_blob():
    q: queue.Queue[dict] = queue.Queue()
    text = draft_domain.stream_structured_blocks(
        client=_MultilineJsonClient(),
        system="system",
        user="user",
        out_queue=q,
        section="引言",
        section_id="H2::引言",
        is_reference=False,
        num_predict=256,
        deadline=time.time() + 10.0,
        strict_json=True,
        text_store=None,
    )
    assert "多行 JSON" in text


def test_stream_structured_blocks_filters_structured_residue_in_plain_recovery():
    q: queue.Queue[dict] = queue.Queue()
    text = draft_domain.stream_structured_blocks(
        client=_JsonResidueClient(),
        system="system",
        user="user",
        out_queue=q,
        section="引言",
        section_id="H2::引言",
        is_reference=False,
        num_predict=256,
        deadline=time.time() + 10.0,
        strict_json=True,
        text_store=None,
    )
    assert "section_id" not in text
    assert "block_id" not in text
    assert "这是可保存的正文内容" in text
