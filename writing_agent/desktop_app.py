"""Desktop App module.

This module belongs to `writing_agent` in the writing-agent codebase.
"""

from __future__ import annotations

import argparse
import logging
import os
import socket
import sys
import threading
import time
from contextlib import closing
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets
from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView

import uvicorn

logger = logging.getLogger(__name__)

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
    raise RuntimeError(f"No available local port in range {base}..{base + tries - 1}")


def _configure_webengine_env() -> None:
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
    except Exception as _exc:
        logger.debug("Ignored error in desktop_app.py: %s", _exc, exc_info=True)

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
        self._closing = False
        self._load_started = False
        self._startup_deadline = time.monotonic() + 30.0
        self.setWindowTitle(APP_TITLE)
        self.resize(1440, 900)

        self.view = QWebEngineView(self)
        profile = QWebEngineProfile.defaultProfile()
        profile.setHttpUserAgent(profile.httpUserAgent() + " WritingAgentDesktop/1.0")
        profile.setHttpCacheType(QWebEngineProfile.NoCache)
        profile.downloadRequested.connect(self._handle_download)
        settings = self.view.settings()
        settings.setAttribute(QWebEngineSettings.JavascriptEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebGLEnabled, False)
        settings.setAttribute(QWebEngineSettings.Accelerated2dCanvasEnabled, False)
        settings.setAttribute(QWebEngineSettings.LocalStorageEnabled, True)
        settings.setAttribute(QWebEngineSettings.PluginsEnabled, False)
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
        act_reload.triggered.connect(self._reload_workbench)
        view_menu.addAction(act_reload)

    def _handle_download(self, download) -> None:
        default = download.downloadFileName() or "document.docx"
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save File", default)
        if not path:
            download.cancel()
            return
        destination = Path(path)
        download.setDownloadDirectory(str(destination.parent))
        download.setDownloadFileName(destination.name)
        download.accept()

    def _on_load_finished(self, ok: bool) -> None:
        if self._closing or not self._load_started:
            return
        if not ok:
            self._show_startup_error("界面加载失败。请检查本地服务后使用 View → Reload 重试。")

    def _reload_workbench(self) -> None:
        if not self._closing:
            self._load_started = True
            self.view.setUrl(QtCore.QUrl(self._url))

    def _show_startup_error(self, message: str) -> None:
        self._load_started = False
        self.view.setHtml(f"<html><body><h2>写作助手启动失败</h2><p>{message}</p></body></html>")

    def _schedule_ready_check(self) -> None:
        if self._closing or self._load_started:
            return
        if self._server.server.started:
            self._load_started = True
            self.view.setUrl(QtCore.QUrl(self._url))
        elif not self._server.is_alive():
            self._show_startup_error("本地服务未能启动，请查看启动窗口中的错误信息。")
        elif time.monotonic() >= self._startup_deadline:
            self._server.stop()
            self._show_startup_error("本地服务启动超过 30 秒，请关闭窗口后重试。")
        else:
            QtCore.QTimer.singleShot(200, self._schedule_ready_check)

    def closeEvent(self, event) -> None:
        self._closing = True
        if self._server:
            self._server.stop()
        super().closeEvent(event)


def main(argv: list[str] | None = None) -> int:
    sys.dont_write_bytecode = True
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
    _configure_webengine_env()
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

    app = QtWidgets.QApplication(sys.argv)
    server = UvicornWorker(host, port)
    server.start()
    url = f"http://{host}:{port}/"
    try:
        window = MainWindow(url, server)
        window.show()
        app.aboutToQuit.connect(server.stop)
        return app.exec()
    finally:
        server.stop()
        server.join(timeout=5)
        if server.is_alive():
            logger.warning("Local service did not stop within 5 seconds")


if __name__ == "__main__":
    raise SystemExit(main())
