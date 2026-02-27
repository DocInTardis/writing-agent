import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_url(url: str, timeout_s: float = 15.0) -> None:
    start = time.time()
    last_err = None
    while time.time() - start < timeout_s:
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                if resp.status < 500:
                    return
        except Exception as exc:  # pragma: no cover - best-effort polling
            last_err = exc
        time.sleep(0.25)
    raise RuntimeError(f"Server not ready: {url} ({last_err})")


@pytest.fixture(scope="session")
def server_url(tmp_path_factory) -> str:
    port = _find_free_port()
    env = os.environ.copy()
    env["WRITING_AGENT_USE_OLLAMA"] = "0"
    env["WRITING_AGENT_RAG_ENABLED"] = "0"
    env["WRITING_AGENT_USE_SVELTE"] = "0"
    env["WRITING_AGENT_HOST"] = "127.0.0.1"
    env["WRITING_AGENT_PORT"] = str(port)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "writing_agent.web.app_v2:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--log-level",
        "warning",
    ]
    proc = subprocess.Popen(cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        _wait_for_url(f"http://127.0.0.1:{port}/favicon.ico")
        yield f"http://127.0.0.1:{port}"
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_workbench_basic_controls(server_url, tmp_path):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        page.goto(server_url, wait_until="domcontentloaded")
        page.wait_for_selector(".app")
        page.wait_for_selector("#btnOpen")
        page.wait_for_selector("#btnSave")
        page.wait_for_selector("#btnDownload")
        page.wait_for_selector("#btnGenerate")
        page.wait_for_selector("#source")
        page.wait_for_selector("#preview", state="attached")
        context.close()
        browser.close()


def test_toolbar_tabs_and_download(server_url, tmp_path):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        page.goto(server_url, wait_until="domcontentloaded")
        page.wait_for_selector(".app")

        page.wait_for_selector("#btnDownload")
        href = page.locator("#btnDownload").get_attribute("href") or ""
        assert "/download/" in href and href.endswith(".docx")

        page.click('.tab[data-tab="preview"]')
        page.wait_for_function("!document.getElementById('preview').classList.contains('hidden')")
        screenshot_path = tmp_path / "workbench_preview.png"
        page.screenshot(path=str(screenshot_path), full_page=True)
        assert screenshot_path.exists()

        page.click('.tab[data-tab="edit"]')
        page.wait_for_function("!document.getElementById('source').classList.contains('hidden')")

        context.close()
        browser.close()
