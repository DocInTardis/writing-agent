"""Desktop App module.

This module belongs to `writing_agent` in the writing-agent codebase.
"""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from contextlib import closing
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView

import uvicorn

from writing_agent.llm import OllamaClient, get_ollama_settings


APP_TITLE = "写作助手"
LOADING_HTML = """<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>写作助手</title>
<style>
body{margin:0;background:#0f1115;color:#e5e7eb;font-family:'Microsoft YaHei',sans-serif;}
.wrap{display:flex;align-items:center;justify-content:center;height:100vh;}
.card{background:#16181d;border:1px solid #262a33;border-radius:16px;padding:28px 32px;max-width:520px;}
.title{font-size:20px;font-weight:700;margin-bottom:8px;}
.muted{font-size:13px;color:#9aa4b2;line-height:1.5;}
</style></head>
<body><div class="wrap"><div class="card">
<div class="title">写作助手正在启动…</div>
<div class="muted">正在加载本地服务与界面，如果稍后仍为空白请稍等片刻或重启。</div>
</div></div></body></html>
"""


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
    return base


def _start_ollama_serve() -> None:
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
    subprocess.Popen(
        ["ollama", "serve"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        creationflags=creationflags,
    )


def _wait_until(predicate, timeout_s: float, interval_s: float = 0.2) -> bool:
    start = time.time()
    while time.time() - start < timeout_s:
        if predicate():
            return True
        time.sleep(interval_s)
    return False


def ensure_ollama_ready() -> None:
    settings = get_ollama_settings()
    if not settings.enabled:
        return
    client = OllamaClient(base_url=settings.base_url, model=settings.model, timeout_s=settings.timeout_s)
    if not client.is_running():
        try:
            _start_ollama_serve()
        except FileNotFoundError:
            return
        _wait_until(client.is_running, timeout_s=10)
    if client.is_running() and not client.has_model():
        client.pull_model()


def _wait_for_http(url: str, timeout_s: float = 15.0) -> bool:
    start = time.time()
    while time.time() - start < timeout_s:
        try:
            with urllib.request.urlopen(url, timeout=2) as resp:
                if resp.status < 500:
                    return True
        except Exception:
            time.sleep(0.3)
    return False


def _configure_webengine_env() -> None:
    os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
    base_flags = [
        "--disable-gpu",
        "--disable-gpu-compositing",
        "--disable-accelerated-2d-canvas",
        "--disable-webgl",
        "--disable-software-rasterizer",
    ]
    existing = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").strip()
    merged = " ".join([existing] + base_flags).strip()
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join(dict.fromkeys(merged.split()))
    os.environ.setdefault("QT_OPENGL", "software")
    try:
        import PySide6  # type: ignore

        base = Path(PySide6.__file__).resolve().parent
        process = base / "Qt" / "libexec" / "QtWebEngineProcess.exe"
        if process.exists():
            os.environ.setdefault("QTWEBENGINEPROCESS_PATH", str(process))
            os.environ.setdefault("QTWEBENGINE_PROCESS_PATH", str(process))
    except Exception:
        pass


class UvicornWorker(threading.Thread):
    def __init__(self, host: str, port: int) -> None:
        super().__init__(daemon=True)
        self.config = uvicorn.Config(
            "writing_agent.web.app_v2:app",
            host=host,
            port=port,
            log_level="warning",
            access_log=False,
        )
        self.server = uvicorn.Server(self.config)

    def run(self) -> None:
        self.server.run()

    def stop(self) -> None:
        self.server.should_exit = True


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, url: str, server: UvicornWorker) -> None:
        super().__init__()
        self._server = server
        self._base_url = url
        self.setWindowTitle(APP_TITLE)
        self.resize(1440, 900)

        self.view = QWebEngineView(self)
        profile = QWebEngineProfile.defaultProfile()
        profile.setHttpUserAgent(profile.httpUserAgent() + " WritingAgentDesktop/1.0")
        profile.setHttpCacheType(QWebEngineProfile.NoCache)
        profile.clearHttpCache()
        profile.downloadRequested.connect(self._handle_download)
        settings = self.view.settings()
        settings.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebGLEnabled, False)
        settings.setAttribute(QWebEngineSettings.Accelerated2dCanvasEnabled, False)
        settings.setAttribute(QWebEngineSettings.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.PluginsEnabled, True)
        settings.setAttribute(QWebEngineSettings.JavascriptCanAccessClipboard, True)

        self._url = url
        self.view.setHtml(LOADING_HTML)
        self.view.loadFinished.connect(self._on_load_finished)
        self.setCentralWidget(self.view)
        self._build_menu()
        self._schedule_ready_check()

    def _run_js(self, script: str) -> None:
        self.view.page().runJavaScript(script)

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        act_new = QtGui.QAction("&New", self)
        act_new.setShortcut(QtGui.QKeySequence.New)
        act_new.triggered.connect(lambda: self.view.setUrl(QtCore.QUrl(self._base_url)))
        file_menu.addAction(act_new)

        act_open = QtGui.QAction("&Open...", self)
        act_open.setShortcut(QtGui.QKeySequence.Open)
        act_open.triggered.connect(lambda: self._run_js("window.__wa_open_file_dialog && window.__wa_open_file_dialog();"))
        file_menu.addAction(act_open)

        act_save = QtGui.QAction("&Save", self)
        act_save.setShortcut(QtGui.QKeySequence.Save)
        act_save.triggered.connect(lambda: self._run_js("window.__wa_save_doc && window.__wa_save_doc();"))
        file_menu.addAction(act_save)

        act_export = QtGui.QAction("Export Docx", self)
        act_export.setShortcut(QtGui.QKeySequence("Ctrl+Shift+S"))
        act_export.triggered.connect(
            lambda: self._run_js("window.__wa_download_docx && window.__wa_download_docx();")
        )
        file_menu.addAction(act_export)

        file_menu.addSeparator()
        act_quit = QtGui.QAction("Quit", self)
        act_quit.setShortcut(QtGui.QKeySequence.Quit)
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        view_menu = self.menuBar().addMenu("&View")
        act_focus = QtGui.QAction("Focus Mode", self)
        act_focus.setShortcut(QtGui.QKeySequence("Ctrl+Shift+F"))
        act_focus.triggered.connect(lambda: self._run_js("window.__wa_toggle_focus && window.__wa_toggle_focus();"))
        view_menu.addAction(act_focus)

        act_reload = QtGui.QAction("Reload", self)
        act_reload.setShortcut(QtGui.QKeySequence.Refresh)
        act_reload.triggered.connect(self.view.reload)
        view_menu.addAction(act_reload)

    def _handle_download(self, download) -> None:
        default = download.path() or os.path.basename(download.url().path()) or "document.docx"
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save File", default)
        if not path:
            download.cancel()
            return
        download.setPath(path)
        download.accept()

    def _on_load_finished(self, ok: bool) -> None:
        if not ok:
            QtCore.QTimer.singleShot(800, self.view.reload)
            return
        try:
            self.view.page().runJavaScript("Boolean(window.__wa_ready)", self._handle_ready_check)
        except Exception:
            QtCore.QTimer.singleShot(800, self.view.reload)

    def _handle_ready_check(self, ready: bool) -> None:
        if ready:
            return
        QtCore.QTimer.singleShot(600, self.view.reload)

    def _schedule_ready_check(self) -> None:
        def _check():
            if _wait_for_http(self._url, timeout_s=8):
                QtCore.QTimer.singleShot(200, self.view.reload)
            else:
                QtCore.QTimer.singleShot(800, self._schedule_ready_check)

        QtCore.QTimer.singleShot(200, _check)

    def closeEvent(self, event) -> None:
        if self._server:
            self._server.stop()
        super().closeEvent(event)


def main() -> int:
    _configure_webengine_env()
    parser = argparse.ArgumentParser(description="Writing Agent Desktop")
    parser.add_argument("--host", default=os.environ.get("WRITING_AGENT_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("WRITING_AGENT_PORT", "8000")))
    parser.add_argument("--no-ollama", action="store_true")
    args = parser.parse_args()

    host = args.host
    port = _pick_port(host, args.port)
    os.environ["WRITING_AGENT_HOST"] = host
    os.environ["WRITING_AGENT_PORT"] = str(port)
    os.environ.setdefault("WRITING_AGENT_USE_OLLAMA", "1")
    os.environ.setdefault("WRITING_AGENT_DESKTOP", "1")
    os.environ.setdefault("WRITING_AGENT_PERF_MODE", "1")

    if not args.no_ollama:
        ensure_ollama_ready()

    server = UvicornWorker(host, port)
    server.start()

    app = QtWidgets.QApplication(sys.argv)
    url = f"http://{host}:{port}/"
    window = MainWindow(url, server)
    window.show()
    QtCore.QTimer.singleShot(300, lambda: window.view.setUrl(QtCore.QUrl(url)))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
