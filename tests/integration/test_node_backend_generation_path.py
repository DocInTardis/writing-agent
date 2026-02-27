from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn
from types import SimpleNamespace

from writing_agent.web import app_v2


class _ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


class _GatewayHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path == "/health":
            payload = json.dumps({"ok": 1}).encode("utf-8")
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("content-length", "0") or "0")
        _ = self.rfile.read(length)
        if self.path == "/v1/stream-text":
            payload = json.dumps(
                {
                    "ok": 1,
                    "text": "## 标题\n\n这是一段通过 node gateway 生成的内容。",
                    "usage": {"prompt_tokens": 10, "completion_tokens": 12, "total_tokens": 22},
                }
            ).encode("utf-8")
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


def _start_gateway():
    server = _ThreadedHTTPServer(("127.0.0.1", 0), _GatewayHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return server, f"http://{host}:{port}"


def test_single_pass_generate_can_use_node_backend(monkeypatch) -> None:
    server, url = _start_gateway()
    try:
        monkeypatch.setenv("WRITING_AGENT_LLM_BACKEND", "node")
        monkeypatch.setenv("WRITING_AGENT_NODE_GATEWAY_URL", url)
        monkeypatch.setenv("WRITING_AGENT_LLM_BACKEND_ROLLOUT_PERCENT", "100")
        monkeypatch.setenv("WRITING_AGENT_LLM_PROVIDER", "ollama")
        monkeypatch.setenv("WRITING_AGENT_NODE_GATEWAY_AUTO_FALLBACK", "1")
        monkeypatch.setattr(
            "writing_agent.llm.factory.get_ollama_settings",
            lambda: SimpleNamespace(enabled=True, base_url="http://127.0.0.1:11434", model="qwen2.5:1.5b", timeout_s=12.0),
        )

        session = SimpleNamespace(
            template_outline=[],
            template_required_h2=[],
        )
        monkeypatch.setattr(
            "writing_agent.web.app_v2.get_ollama_settings",
            lambda: SimpleNamespace(enabled=True, base_url="http://127.0.0.1:11434", model="qwen2.5:1.5b", timeout_s=12.0),
        )

        out = app_v2._single_pass_generate(
            session,
            instruction="写一段测试文字",
            current_text="",
            target_chars=0,
        )
        assert "node gateway" in out
    finally:
        server.shutdown()
        server.server_close()
