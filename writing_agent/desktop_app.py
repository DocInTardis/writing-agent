"""Lightweight desktop shell backed by the system WebView2 runtime."""

from __future__ import annotations

import argparse
import logging
import os
import socket
import sys
import threading
import time
from contextlib import closing

import uvicorn
import webview

logger = logging.getLogger(__name__)
APP_TITLE = "写作助手"
LOADING_HTML = """<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>写作助手</title><style>
body{margin:0;background:#0f1115;color:#e5e7eb;font-family:'Microsoft YaHei',sans-serif}
.wrap{display:flex;align-items:center;justify-content:center;height:100vh}
.card{background:#16181d;border:1px solid #262a33;border-radius:16px;padding:28px 32px;max-width:520px}
.title{font-size:20px;font-weight:700;margin-bottom:8px}.muted{font-size:13px;color:#9aa4b2;line-height:1.5}
</style></head><body><div class="wrap"><div class="card"><div class="title">写作助手正在启动…</div>
<div class="muted">正在加载本地服务与界面。</div></div></div></body></html>"""


def _error_html(message: str) -> str:
    return (
        "<!doctype html><html lang='zh-CN'><meta charset='utf-8'><body>"
        f"<h2>写作助手启动失败</h2><p>{message}</p></body></html>"
    )


def _port_available(host: str, port: int) -> bool:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
        except OSError:
            return False
    return True


def _pick_port(host: str, base: int, tries: int = 20) -> int:
    for offset in range(tries):
        port = base + offset
        if _port_available(host, port):
            return port
    raise RuntimeError(f"No available local port in range {base}..{base + tries - 1}")


class UvicornWorker(threading.Thread):
    def __init__(self, host: str, port: int) -> None:
        super().__init__(daemon=True)
        self.config = uvicorn.Config(
            "writing_agent.web.app_v2:app", host=host, port=port,
            log_level="warning", access_log=False,
        )
        self.server = uvicorn.Server(self.config)

    def run(self) -> None:
        self.server.run()

    def stop(self) -> None:
        self.server.should_exit = True


def _load_when_ready(window, server: UvicornWorker, url: str, *, timeout_s: float = 30.0) -> None:
    deadline = time.monotonic() + max(0.1, float(timeout_s))
    wake = threading.Event()
    while server.is_alive() and not server.server.started and time.monotonic() < deadline:
        wake.wait(0.05)
    if server.server.started:
        window.load_url(url)
        return
    server.stop()
    message = (
        "本地服务启动超过 30 秒，请关闭窗口后重试。"
        if server.is_alive()
        else "本地服务未能启动，请查看启动窗口中的错误信息。"
    )
    window.load_html(_error_html(message))


def main(argv: list[str] | None = None) -> int:
    sys.dont_write_bytecode = True
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    parser = argparse.ArgumentParser(description="Writing Agent Desktop")
    parser.add_argument("--host", default=os.environ.get("WRITING_AGENT_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("WRITING_AGENT_PORT", "8000")))
    args = parser.parse_args(argv)

    host = args.host
    port = _pick_port(host, args.port)
    os.environ["WRITING_AGENT_HOST"] = host
    os.environ["WRITING_AGENT_PORT"] = str(port)
    os.environ.setdefault("WRITING_AGENT_DESKTOP", "1")
    os.environ.setdefault("WRITING_AGENT_PERF_MODE", "1")

    server = UvicornWorker(host, port)
    url = f"http://{host}:{port}/"
    webview.settings["ALLOW_DOWNLOADS"] = True
    window = webview.create_window(
        APP_TITLE, html=LOADING_HTML, width=1440, height=900,
        min_size=(960, 640), confirm_close=False,
    )
    window.events.closed += server.stop
    server.start()
    try:
        webview.start(
            _load_when_ready,
            args=(window, server, url),
            gui="edgechromium" if os.name == "nt" else None,
            private_mode=True,
            user_agent="WritingAgentDesktop/1.0",
        )
        return 0
    finally:
        server.stop()
        server.join(timeout=5)
        if server.is_alive():
            logger.warning("Local service did not stop within 5 seconds")


if __name__ == "__main__":
    raise SystemExit(main())
