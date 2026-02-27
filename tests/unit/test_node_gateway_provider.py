from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

from writing_agent.llm.providers.node_ai_gateway_provider import NodeAIGatewayProvider, NodeGatewayConfig


class _ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class _GatewayHandler(BaseHTTPRequestHandler):
    def _json(self, payload: dict, status: int = 200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):  # noqa: N802
        if self.path == "/health":
            self._json({"ok": 1})
            return
        self._json({"ok": 0}, status=404)

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("content-length", "0") or "0")
        raw = self.rfile.read(length).decode("utf-8", errors="ignore")
        data = json.loads(raw or "{}")
        if self.path == "/v1/stream-text":
            if data.get("stream") is False:
                self._json({"ok": 1, "text": "gateway text", "usage": {}})
                return
            body = (
                'data: {"type":"text-delta","delta":"a"}\n\n'
                'data: {"type":"text-delta","delta":"b"}\n\n'
                'data: {"type":"done","text":"ab","usage":{}}\n\n'
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("content-type", "text/event-stream")
            self.send_header("content-length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/v1/generate-object":
            self._json({"ok": 1, "object": {"ok": 1, "from": "gateway"}})
            return
        if self.path == "/v1/tool-call":
            self._json({"ok": 1, "result": {"ok": 1, "tool": "echo"}})
            return
        self._json({"ok": 0}, status=404)

    def log_message(self, format: str, *args):  # noqa: A003
        return


def _start_gateway():
    server = _ThreadedHTTPServer(("127.0.0.1", 0), _GatewayHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, f"http://{host}:{port}"


def test_node_gateway_provider_chat_and_stream() -> None:
    server, url = _start_gateway()
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
        assert provider.is_running() is True
        assert provider.chat(system="s", user="u") == "gateway text"
        assert "".join(provider.chat_stream(system="s", user="u")) == "ab"
    finally:
        server.shutdown()
        server.server_close()


def test_node_gateway_provider_generate_object_and_tool_call() -> None:
    server, url = _start_gateway()
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
        obj = provider.generate_object(
            system="s",
            user="u",
            schema={"type": "object", "properties": {"ok": {"type": "number"}}},
        )
        assert obj.get("ok") == 1
        out = provider.tool_call(tool_name="echo", arguments={"a": 1})
        assert out.get("ok") == 1
    finally:
        server.shutdown()
        server.server_close()


def test_node_gateway_provider_auto_fallback_on_failure() -> None:
    class _Fallback:
        def chat(self, *, system, user, temperature=0.2, options=None):
            return "fallback-text"

        def chat_stream(self, *, system, user, temperature=0.2, options=None):
            yield "fallback-"
            yield "stream"

        def embeddings(self, *, prompt, model=None):
            return [0.1, 0.2]

    provider = NodeAIGatewayProvider(
        config=NodeGatewayConfig(
            gateway_url="http://127.0.0.1:9",
            model="mock-model",
            timeout_s=0.2,
            max_retries=1,
            auto_fallback=True,
        ),
        fallback_provider=_Fallback(),
    )
    assert provider.chat(system="s", user="u") == "fallback-text"
    assert "".join(provider.chat_stream(system="s", user="u")) == "fallback-stream"
