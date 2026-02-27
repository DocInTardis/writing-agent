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
    env["WRITING_AGENT_USE_SVELTE"] = "1"
    env["WRITING_AGENT_HOST"] = "127.0.0.1"
    env["WRITING_AGENT_PORT"] = str(port)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
    frontend_dir = Path(__file__).resolve().parents[2] / "writing_agent" / "web" / "frontend_svelte"
    subprocess.run(
        ["npm.cmd", "run", "build"],
        cwd=str(frontend_dir),
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
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


def test_workbench_svelte_render_and_screenshot(server_url, tmp_path):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        page.goto(server_url, wait_until="domcontentloaded")
        page.wait_for_selector(".app")
        page.wait_for_selector(".editable")
        page.wait_for_function("window.__waGetStore && window.__waGetStore('docId')")
        doc_id = page.evaluate("window.__waGetStore('docId')")
        assert doc_id
        page.evaluate(
            """
            async ({ docId }) => {
              await fetch(`/api/doc/${docId}/save`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  text: '# Test Title\\n\\n## Intro\\n\\nFirst paragraph.\\n\\n1. Item one\\n2. Item two'
                })
              });
            }
            """,
            {"docId": doc_id},
        )
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector(".app")
        page.wait_for_selector(".editable")
        page.wait_for_selector(".wa-doc")
        page.wait_for_selector(".wa-footer", state="attached")
        page.wait_for_function(
            "document.querySelector('.editable') && document.querySelector('.editable').innerText.includes('Item two')"
        )
        page.wait_for_function("window.__waGetStore && window.__waGetStore('docIr')")

        screenshot_path = tmp_path / "workbench_svelte.png"
        page.screenshot(path=str(screenshot_path), full_page=True, timeout=120000)
        assert screenshot_path.exists()

        block_id = page.eval_on_selector(".editable p[data-block-id]", "el => el.dataset.blockId")
        assert block_id
        doc_ir_snapshot = page.evaluate("window.__waGetStore('docIr')")
        assert block_id in str(doc_ir_snapshot)
        page.click(".editable p[data-block-id]", modifiers=["Alt"])
        page.wait_for_selector(".inline-selection-bar")
        page.click(".inline-selection-bar .mini-btn")
        page.wait_for_selector(".inline-edit-popover")
        page.fill(".inline-edit-popover .inline-instruction", "replace with Updated paragraph.")
        with page.expect_response("**/block-edit/preview") as resp_info:
            page.evaluate("document.querySelector('.inline-edit-popover .btn.primary')?.click()")
        resp = resp_info.value
        assert resp.ok
        req_payload = resp.request.post_data_json
        assert block_id in str(req_payload.get("doc_ir", {}))
        data = resp.json()
        candidates = data.get("candidates") or []
        assert isinstance(candidates, list)
        assert len(candidates) > 0
        assert block_id in str(candidates[0].get("doc_ir", {}))
        page.wait_for_selector(".candidate-card")

        screenshot_path2 = tmp_path / "workbench_svelte_block_edit.png"
        page.screenshot(path=str(screenshot_path2), full_page=True, timeout=120000)
        assert screenshot_path2.exists()

        context.close()
        browser.close()


def test_workbench_svelte_shortcuts_and_toolbar_state(server_url, tmp_path):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        page.goto(server_url, wait_until="domcontentloaded")
        page.wait_for_selector(".app")
        page.wait_for_selector(".editable")
        page.wait_for_function("window.__waGetStore && window.__waGetStore('docId')")
        doc_id = page.evaluate("window.__waGetStore('docId')")
        assert doc_id

        page.evaluate(
            """
            async ({ docId }) => {
              await fetch(`/api/doc/${docId}/save`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  text: '# Shortcut Test\\n\\n## Intro\\n\\nabc'
                })
              });
            }
            """,
            {"docId": doc_id},
        )
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector(".editable p[data-block-id]")
        page.wait_for_function(
            "document.querySelector('.editable') && document.querySelector('.editable').innerText.includes('abc')"
        )

        para = page.locator(".editable p[data-block-id]").first
        para.click()
        page.keyboard.press("End")
        page.keyboard.type("XYZ")
        page.wait_for_timeout(120)
        assert "abcXYZ" in para.inner_text()

        undo_btn = page.locator('button.tool-btn[title*="Ctrl/Cmd+Z"]').first
        redo_btn = page.locator('button.tool-btn[title*="Ctrl/Cmd+Y"]').first
        assert not undo_btn.evaluate("el => el.disabled")

        page.keyboard.press("Control+z")
        page.wait_for_timeout(220)
        assert para.inner_text() == "abc"
        assert not redo_btn.evaluate("el => el.disabled")

        page.keyboard.press("Control+y")
        page.wait_for_timeout(220)
        assert para.inner_text() == "abcXYZ"

        screenshot_path = tmp_path / "workbench_svelte_shortcuts.png"
        page.screenshot(path=str(screenshot_path), full_page=True, timeout=120000)
        assert screenshot_path.exists()

        context.close()
        browser.close()


def test_workbench_svelte_empty_focus_placeholder_alignment(server_url, tmp_path):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        page.goto(server_url, wait_until="domcontentloaded")
        page.wait_for_selector(".app")
        page.wait_for_selector(".editable")
        page.wait_for_function("window.__waGetStore && window.__waGetStore('docId')")
        doc_id = page.evaluate("window.__waGetStore('docId')")
        assert doc_id

        page.evaluate(
            """
            async ({ docId }) => {
              await fetch(`/api/doc/${docId}/save`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: '' })
              });
            }
            """,
            {"docId": doc_id},
        )
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector(".editable")
        page.wait_for_selector(".editable [data-block-id]")

        before_opacity = page.evaluate(
            """
            () => {
              const editable = document.querySelector('.editable');
              if (!editable) return null;
              return getComputedStyle(editable, '::before').opacity;
            }
            """
        )
        assert before_opacity is not None

        page.click(".editable [data-block-id]")
        page.wait_for_timeout(80)

        after_opacity = page.evaluate(
            """
            () => {
              const editable = document.querySelector('.editable');
              if (!editable) return null;
              return getComputedStyle(editable, '::before').opacity;
            }
            """
        )
        assert after_opacity is not None
        assert float(after_opacity) <= 0.1

        text_indent = page.evaluate(
            """
            () => {
              const p = document.querySelector('.editable [data-block-id]');
              if (!p) return null;
              return getComputedStyle(p).textIndent;
            }
            """
        )
        assert text_indent is not None
        assert abs(float(str(text_indent).replace('px', '').strip() or '0')) <= 0.5

        text_style = page.evaluate(
            """
            () => {
              const p = document.querySelector('.editable [data-block-id]');
              if (!p) return null;
              const cs = getComputedStyle(p);
              return {
                fontFamily: cs.fontFamily || '',
                textShadow: cs.textShadow || '',
                textDecorationLine: cs.textDecorationLine || ''
              };
            }
            """
        )
        assert text_style is not None
        assert "times new roman" not in str(text_style.get("fontFamily", "")).lower()
        assert "simsun" not in str(text_style.get("fontFamily", "")).lower()
        assert str(text_style.get("textShadow", "")).lower() == "none"
        assert "line-through" not in str(text_style.get("textDecorationLine", "")).lower()

        page.keyboard.type("A")
        page.wait_for_function(
            "document.querySelector('.editable') && document.querySelector('.editable').innerText.includes('A')"
        )

        screenshot_path = tmp_path / "workbench_svelte_empty_focus.png"
        page.screenshot(path=str(screenshot_path), full_page=True, timeout=120000)
        assert screenshot_path.exists()

        context.close()
        browser.close()


def test_workbench_svelte_a4_layout_and_heading_glue(server_url, tmp_path):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True, viewport={"width": 1440, "height": 900})
        page = context.new_page()
        page.goto(server_url, wait_until="domcontentloaded")
        page.wait_for_selector(".app")
        page.wait_for_selector(".editable")
        page.wait_for_function("window.__waGetStore && window.__waGetStore('docId')")
        doc_id = page.evaluate("window.__waGetStore('docId')")
        assert doc_id

        source_text = (
            "# A4 Regression\\n\\n"
            "2. 关键技术\\n"
            "2.1 计算机视觉与图像处理计算机视觉作为人工智能的重要分支，在自动驾驶中发挥关键作用。\\n"
        )
        page.evaluate(
            """
            async ({ docId, text }) => {
              await fetch(`/api/doc/${docId}/save`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text })
              });
            }
            """,
            {"docId": doc_id, "text": source_text},
        )
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector(".editor.paper .editable")
        page.wait_for_function(
            "document.querySelector('.editable') && document.querySelector('.editable').innerText.includes('关键技术')"
        )
        page.wait_for_function(
            "document.querySelector('.editable') && document.querySelector('.editable').innerText.includes('计算机视觉与图像处理')"
        )

        width = page.evaluate(
            """
            () => {
              const el = document.querySelector('.editor.paper .editable');
              if (!el) return null;
              return el.getBoundingClientRect().width;
            }
            """
        )
        assert width is not None
        assert 760 <= float(width) <= 840

        heading_align = page.evaluate(
            """
            () => {
              const target = document.querySelector('.editable h2');
              if (!target) return 'center';
              return getComputedStyle(target).textAlign || '';
            }
            """
        )
        assert str(heading_align).lower() == "center"

        split_state = page.evaluate(
            """
            () => {
              const root = document.querySelector('.editable');
              if (!root) return null;
              const mode = root.getAttribute('data-render-mode') || '';
              const headingTexts = Array.from(root.querySelectorAll('h1, h2, h3')).map((el) => (el.textContent || '').trim());
              const hasMultiHeading = headingTexts.length >= 2;
              const hasGluedHeading = headingTexts.some((t) => t.includes('作为人工智能'));
              const hasBody = (root.innerText || '').includes('计算机视觉作为人工智能的重要分支');
              return {
                mode,
                hasMultiHeading,
                hasGluedHeading,
                hasBody,
                rawText: root.innerText || ''
              };
            }
            """
        )
        assert split_state is not None
        mode = str(split_state.get("mode") or "")
        if mode == "doc":
            assert not bool(split_state.get("hasGluedHeading"))
            assert bool(split_state.get("hasBody"))
        else:
            assert "2.1 计算机视觉与图像处理计算机视觉作为人工智能的重要分支" in str(split_state.get("rawText") or "")

        screenshot_path = tmp_path / "workbench_svelte_a4_heading_glue.png"
        page.screenshot(path=str(screenshot_path), full_page=True, timeout=120000)
        assert screenshot_path.exists()

        context.close()
        browser.close()


def test_workbench_svelte_generate_with_existing_text_confirms_continue_mode(server_url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        page.goto(server_url, wait_until="domcontentloaded")
        page.wait_for_selector(".app")
        page.wait_for_selector(".editable")
        page.wait_for_function("window.__waGetStore && window.__waGetStore('docId')")
        doc_id = page.evaluate("window.__waGetStore('docId')")
        assert doc_id

        page.evaluate(
            """
            async ({ docId }) => {
              await fetch(`/api/doc/${docId}/save`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  text: '# Existing\\n\\n## Intro\\n这里已经有足够长度的正文内容，用来触发续写确认弹窗。'
                })
              });
            }
            """,
            {"docId": doc_id},
        )
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector(".assistant-dock textarea")
        page.wait_for_function(
            "window.__waGetStore && String(window.__waGetStore('sourceText') || '').includes('这里已经有足够长度')"
        )

        captured_payload: dict = {}
        dialogs: list[str] = []

        def _on_dialog(dialog):
            dialogs.append(dialog.message)
            dialog.accept()

        page.on("dialog", _on_dialog)

        def _on_generate(route, request):
            if request.method != "POST":
                route.continue_()
                return
            payload = request.post_data_json
            if isinstance(payload, dict):
                captured_payload.update(payload)
            body = 'event: final\ndata: {"text":"# Existing\\n\\n## Intro\\n续写完成"}\n\n'
            try:
                route.fulfill(
                    status=200,
                    headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"},
                    body=body,
                )
            except Exception:
                return

        page.route("**/api/doc/*/generate/stream", _on_generate)

        page.fill(".assistant-dock textarea", "请补充结论段")
        page.click(".assistant-dock .send-btn")

        start = time.time()
        while not captured_payload and (time.time() - start) < 5:
            page.wait_for_timeout(100)

        assert dialogs, "expected continue/overwrite confirmation dialog"
        assert "检测到编辑区已有内容" in dialogs[0]
        assert captured_payload.get("compose_mode") == "continue"
        assert "用户需求" in str(captured_payload.get("instruction") or "")

        context.close()
        browser.close()


def test_workbench_svelte_generate_with_existing_text_confirms_overwrite_mode(server_url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        page.goto(server_url, wait_until="domcontentloaded")
        page.wait_for_selector(".app")
        page.wait_for_selector(".editable")
        page.wait_for_function("window.__waGetStore && window.__waGetStore('docId')")
        doc_id = page.evaluate("window.__waGetStore('docId')")
        assert doc_id

        existing_text = (
            "# Existing\\n\\n## Intro\\n"
            "This draft already has meaningful content and should trigger compose mode confirmation."
        )
        page.evaluate(
            """
            async ({ docId, text }) => {
              await fetch(`/api/doc/${docId}/save`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text })
              });
            }
            """,
            {"docId": doc_id, "text": existing_text},
        )
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector(".assistant-dock textarea")
        page.wait_for_function(
            "window.__waGetStore && String(window.__waGetStore('sourceText') || '').includes('meaningful content')"
        )

        captured_payload: dict = {}
        dialogs: list[str] = []

        def _on_dialog(dialog):
            dialogs.append(dialog.message)
            dialog.dismiss()

        page.on("dialog", _on_dialog)

        def _on_generate(route, request):
            if request.method != "POST":
                route.continue_()
                return
            payload = request.post_data_json
            if isinstance(payload, dict):
                captured_payload.update(payload)
            body = 'event: final\\ndata: {"text":"# Rewritten\\\\n\\\\n## Intro\\\\nFresh overwrite content."}\\n\\n'
            try:
                route.fulfill(
                    status=200,
                    headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"},
                    body=body,
                )
            except Exception:
                return

        page.route("**/api/doc/*/generate/stream", _on_generate)

        user_inst = "Please complete this draft into a final version."
        page.fill(".assistant-dock textarea", user_inst)
        page.click(".assistant-dock .send-btn")

        start = time.time()
        while not captured_payload and (time.time() - start) < 5:
            page.wait_for_timeout(100)

        assert dialogs, "expected continue/overwrite confirmation dialog"
        assert captured_payload.get("compose_mode") == "overwrite"
        request_instruction = str(captured_payload.get("instruction") or "")
        assert user_inst in request_instruction
        assert request_instruction != user_inst

        context.close()
        browser.close()
