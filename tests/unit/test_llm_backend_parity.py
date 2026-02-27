from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

from writing_agent.llm.ai_sdk_adapter import AISDKAdapter
from writing_agent.llm.providers.node_ai_gateway_provider import NodeAIGatewayProvider, NodeGatewayConfig


class _ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class _GatewayHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        payload = json.dumps({"ok": 1}).encode("utf-8")
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("content-length", "0") or "0")
        _ = self.rfile.read(length)
        if self.path == "/v1/stream-text":
            payload = json.dumps({"ok": 1, "text": '{"ok":1,"value":2}'}).encode("utf-8")
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if self.path == "/v1/generate-object":
            payload = json.dumps({"ok": 1, "object": {"ok": 1, "value": 2}}).encode("utf-8")
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if self.path == "/v1/tool-call":
            payload = json.dumps({"ok": 1, "result": {"ok": 1, "value": 2}}).encode("utf-8")
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format: str, *args):  # noqa: A003
        return


class _PythonProvider:
    def chat_stream(self, *, system, user, temperature=0.2, options=None):
        yield '{"ok":1,"value":2}'

    def chat(self, *, system, user, temperature=0.2, options=None):
        return '{"ok":1,"value":2}'


def _start_gateway():
    server = _ThreadedHTTPServer(("127.0.0.1", 0), _GatewayHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, f"http://{host}:{port}"


def test_python_and_node_backend_output_shape_parity() -> None:
    server, url = _start_gateway()
    try:
        py_sdk = AISDKAdapter(provider=_PythonProvider())
        node_provider = NodeAIGatewayProvider(
            config=NodeGatewayConfig(gateway_url=url, model="mock-model", timeout_s=3.0, max_retries=1, auto_fallback=False)
        )
        node_sdk = AISDKAdapter(provider=node_provider)

        py_obj = py_sdk.generate_object(system="s", user="u")
        node_obj = node_sdk.generate_object(system="s", user="u", schema={"type": "object"})

        assert set(py_obj.keys()) == {"ok", "value"}
        assert set(node_obj.keys()) == {"ok", "value"}
        assert py_obj["ok"] == node_obj["ok"] == 1
    finally:
        server.shutdown()
        server.server_close()
