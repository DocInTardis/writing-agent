from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

from writing_agent.llm.providers.node_ai_gateway_provider import NodeAIGatewayProvider, NodeGatewayConfig
from writing_agent.llm.providers.openai_compatible_provider import OpenAICompatibleProvider
from writing_agent.v2 import graph_reference_domain
from writing_agent.v2 import graph_runner_post_domain
from writing_agent.v2 import graph_runner_runtime as runtime_module


CN_BODY = '中文正文'
CN_FLOW = '流程图示'
MOJIBAKE_BODY = CN_BODY.encode("utf-8").decode("latin-1")
MOJIBAKE_FLOW = CN_FLOW.encode("utf-8").decode("latin-1")
RAW_QUERY = '《面向高校科研场景的智能写作代理系统设计与实现》中文学术论文写作需求'
TOPIC_ONLY = '面向高校科研场景的智能写作代理系统设计与实现'
META_TAIL = '中文学术论文写作需求'
KW_SCENE = '高校科研场景'
KW_AGENT = '智能写作代理系统'
KW_REF = '参考文献'
KW_RESULT = '实验结果与分析'
KW_SYSTEM = '系统设计'
INSTRUCTION = '请围绕《面向高校科研场景的智能写作代理系统设计与实现》生成一篇完整的中文学术论文。'


class _ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class _Utf8SSEHandler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("content-length", "0") or "0")
        _ = self.rfile.read(length)
        if self.path == "/chat/completions":
            chunks = [
                {"choices": [{"delta": {"content": MOJIBAKE_BODY[:6]}}]},
                {"choices": [{"delta": {"content": MOJIBAKE_BODY[6:]}}]},
            ]
            body = "".join(f"data: {json.dumps(row, ensure_ascii=False)}\n\n" for row in chunks) + "data: [DONE]\n\n"
            data = body.encode("utf-8")
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if self.path == "/v1/stream-text":
            chunks = [
                {"type": "text-delta", "delta": MOJIBAKE_FLOW[:6]},
                {"type": "text-delta", "delta": MOJIBAKE_FLOW[6:]},
                {"type": "done", "text": MOJIBAKE_FLOW, "usage": {}},
            ]
            body = "".join(f"data: {json.dumps(row, ensure_ascii=False)}\n\n" for row in chunks)
            data = body.encode("utf-8")
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.send_header("content-length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format: str, *args):  # noqa: A003
        return


def _start_server():
    server = _ThreadedHTTPServer(("127.0.0.1", 0), _Utf8SSEHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, f"http://{host}:{port}"


def test_openai_compatible_provider_stream_repairs_mojibake() -> None:
    server, url = _start_server()
    try:
        provider = OpenAICompatibleProvider(base_url=url, api_key="test-key", model="mock-model", timeout_s=3.0)
        assert "".join(provider.chat_stream(system="s", user="u")) == CN_BODY
    finally:
        server.shutdown()
        server.server_close()


def test_node_gateway_provider_stream_repairs_mojibake() -> None:
    server, url = _start_server()
    try:
        provider = NodeAIGatewayProvider(
            config=NodeGatewayConfig(
                gateway_url=url,
                model="mock-model",
                timeout_s=3.0,
                max_retries=1,
                auto_fallback=False,
            )
        )
        assert "".join(provider.chat_stream(system="s", user="u")) == CN_FLOW
    finally:
        server.shutdown()
        server.server_close()


def test_reference_query_normalization_and_ai_matching() -> None:
    cleaned = graph_reference_domain.normalize_reference_query(RAW_QUERY)
    assert META_TAIL not in cleaned
    assert TOPIC_ONLY in cleaned
    score = graph_reference_domain.source_relevance_score(
        query=cleaned,
        source={"title": "An Agentic Writing Assistant for Academic Research Workflows", "source": "openalex"},
    )
    assert score > 0


def test_runtime_derive_reference_query_filters_section_keywords() -> None:
    query = runtime_module._derive_reference_query(
        analysis={
            "topic": RAW_QUERY,
            "keywords": [KW_SCENE, KW_AGENT, KW_SYSTEM, KW_REF, KW_RESULT],
        },
        analysis_summary="",
        instruction=INSTRUCTION,
    )
    assert META_TAIL not in query
    assert KW_REF not in query
    assert KW_RESULT not in query
    assert TOPIC_ONLY in query


def test_plan_title_prefers_chinese_book_quote() -> None:
    title = graph_runner_post_domain._guess_title(INSTRUCTION)
    assert title == TOPIC_ONLY


def test_sections_from_outline_keeps_top_level_h2_when_reference_is_h1() -> None:
    outline = [
        (2, '摘要'),
        (2, '关键词'),
        (2, '引言'),
        (2, '需求分析'),
        (1, '参考文献'),
    ]
    sections, chapters = graph_runner_post_domain._sections_from_outline(outline, expand=False)
    assert sections == [
        'H2::摘要',
        'H2::关键词',
        'H2::引言',
        'H2::需求分析',
        'H2::参考文献',
    ]
    assert chapters == [
        '摘要',
        '关键词',
        '引言',
        '需求分析',
        '参考文献',
    ]
