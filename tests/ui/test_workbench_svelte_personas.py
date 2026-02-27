import base64
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest
from playwright.sync_api import Page, sync_playwright


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
def server_url() -> str:
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


def _open_page(page: Page, server_url: str) -> str:
    page.goto(server_url, wait_until="domcontentloaded")
    page.wait_for_selector(".app")
    page.wait_for_selector(".editable")
    page.wait_for_function("window.__waGetStore && window.__waGetStore('docId')")
    doc_id = page.evaluate("window.__waGetStore('docId')")
    assert doc_id
    return str(doc_id)


def _seed_doc(page: Page, doc_id: str, text: str) -> None:
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
        {"docId": doc_id, "text": text},
    )


def _send_assistant(page: Page, instruction: str) -> None:
    page.fill(".assistant-dock textarea", instruction)
    page.click(".assistant-dock .send-btn")


def _wait_until(predicate, timeout_s: float = 8.0) -> None:
    start = time.time()
    while time.time() - start < timeout_s:
        if predicate():
            return
        time.sleep(0.1)
    raise AssertionError("condition not met in time")


def test_reliability_queue_instruction_while_busy(server_url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        _open_page(page, server_url)

        payloads: list[dict] = []
        dialogs: list[str] = []

        page.on("dialog", lambda dialog: (dialogs.append(dialog.message), dialog.accept()))

        def _on_generate(route, request):
            if request.method != "POST":
                route.continue_()
                return
            payload = request.post_data_json
            payloads.append(payload if isinstance(payload, dict) else {})
            if len(payloads) == 1:
                long_text = "# First Draft\n\n" + ("Long generated paragraph. " * 90)
                body = f"event: final\ndata: {json.dumps({'text': long_text})}\n\n"
            else:
                follow_text = "# Follow-up\n\nSecond request done."
                body = f"event: final\ndata: {json.dumps({'text': follow_text})}\n\n"
            route.fulfill(
                status=200,
                headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"},
                body=body,
            )

        page.route("**/api/doc/*/generate/stream", _on_generate)

        _send_assistant(page, "Write the first version of this report.")
        page.wait_for_timeout(80)
        _send_assistant(page, "Please continue writing and add the methods section.")

        _wait_until(lambda: len(payloads) >= 1, timeout_s=8)
        page.wait_for_selector(".assistant-queue-badge")
        assert page.inner_text(".assistant-queue-badge").strip() == "1"

        assert payloads[0].get("instruction")
        assert not dialogs

        context.close()
        browser.close()


def test_reliability_edit_attempt_during_generation_no_crash(server_url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        doc_id = _open_page(page, server_url)
        _seed_doc(page, doc_id, "# Safety\n\n## Intro\nInitial content.")
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector(".editable")

        errors: list[str] = []
        page.on("pageerror", lambda err: errors.append(str(err)))

        def _on_generate(route, request):
            if request.method != "POST":
                route.continue_()
                return
            long_text = "# Generated\n\n" + ("Stability output paragraph. " * 220)
            body = f"event: final\ndata: {json.dumps({'text': long_text})}\n\n"
            route.fulfill(
                status=200,
                headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"},
                body=body,
            )

        page.route("**/api/doc/*/generate/stream", _on_generate)

        _send_assistant(page, "Generate a long draft for stability test.")
        page.wait_for_timeout(120)
        page.click(".editable")
        page.keyboard.type("LOCAL_EDIT_ATTEMPT")
        page.wait_for_function("window.__waGetStore && window.__waGetStore('generating') === false")
        page.wait_for_timeout(300)

        source_text = str(page.evaluate("window.__waGetStore('sourceText') || ''"))
        assert "Stability output paragraph" in source_text
        assert not errors

        context.close()
        browser.close()


def test_reliability_partial_stream_abort_autosave_and_reload(server_url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        _open_page(page, server_url)

        cached_line = "Cached partial paragraph before abort."

        def _on_generate(route, request):
            if request.method != "POST":
                route.continue_()
                return
            events = [
                ("plan", {"title": "Resume Test", "sections": ["Methods"]}),
                ("section", {"phase": "start", "section": "Methods"}),
                ("section", {"phase": "delta", "section": "Methods", "delta": f"\n{cached_line}\n"}),
                ("section", {"phase": "end", "section": "Methods"}),
            ]
            body = "".join(
                f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n" for name, data in events
            )
            route.fulfill(
                status=200,
                headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"},
                body=body,
            )

        page.route("**/api/doc/*/generate/stream", _on_generate)

        _send_assistant(page, "Generate methods section.")
        page.wait_for_function(
            "window.__waGetStore && String(window.__waGetStore('sourceText') || '').includes('Cached partial paragraph before abort.')"
        )
        page.wait_for_function("window.__waGetStore && window.__waGetStore('generating') === false")
        page.wait_for_timeout(3600)

        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector(".editable")
        page.wait_for_function(
            "window.__waGetStore && String(window.__waGetStore('sourceText') || '').includes('Cached partial paragraph before abort.')"
        )

        context.close()
        browser.close()


def test_reliability_resume_button_replays_interrupted_instruction(server_url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        _open_page(page, server_url)

        payloads: list[dict] = []
        call_count = {"n": 0}

        def _on_generate(route, request):
            if request.method != "POST":
                route.continue_()
                return
            payload = request.post_data_json
            if isinstance(payload, dict):
                payloads.append(payload)
            call_count["n"] += 1
            if call_count["n"] == 1:
                events = [
                    ("plan", {"title": "Resume Flow", "sections": ["Intro", "Methods"]}),
                    ("section", {"phase": "start", "section": "Intro"}),
                    ("section", {"phase": "delta", "section": "Intro", "delta": "\npartial before interrupt\n"}),
                    ("section", {"phase": "end", "section": "Intro"}),
                ]
                body = "".join(
                    f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n" for name, data in events
                )
            else:
                body = 'event: final\ndata: {"text":"# Resume Flow\\n\\n## Intro\\nkept\\n\\n## Methods\\nresumed final content"}\n\n'
            route.fulfill(
                status=200,
                headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"},
                body=body,
            )

        page.route("**/api/doc/*/generate/stream", _on_generate)

        _send_assistant(page, "Please continue this draft.")
        page.wait_for_function("window.__waGetStore && window.__waGetStore('generating') === false")
        page.wait_for_selector("button:has-text('续跑')", timeout=3000)
        page.click("button:has-text('续跑')")
        page.wait_for_function("window.__waGetStore && window.__waGetStore('generating') === false")
        page.wait_for_function(
            "window.__waGetStore && String(window.__waGetStore('sourceText') || '').includes('resumed final content')"
        )

        assert len(payloads) >= 2
        assert payloads[1].get("compose_mode") == "continue"
        assert payloads[1].get("resume_sections") == ["Methods"]

        context.close()
        browser.close()


def test_reliability_section_retry_resume_after_failure(server_url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        _open_page(page, server_url)

        retry_payload: dict = {}

        def _on_generate(route, request):
            if request.method != "POST":
                route.continue_()
                return
            events = [
                ("section_error", {"section": "Methods", "reason": "timeout"}),
                ("final", {"text": "# Retry Demo\n\n## Methods\n(incomplete)\n"}),
            ]
            body = "".join(
                f"event: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n" for name, data in events
            )
            route.fulfill(
                status=200,
                headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"},
                body=body,
            )

        def _on_save(route, request):
            if request.method != "POST":
                route.continue_()
                return
            route.fulfill(
                status=200,
                headers={"Content-Type": "application/json"},
                body=json.dumps({"ok": 1}),
            )

        def _on_doc_ir_ops(route, request):
            if request.method != "POST":
                route.continue_()
                return
            route.fulfill(
                status=200,
                headers={"Content-Type": "application/json"},
                body=json.dumps({"ok": 1}),
            )

        def _on_retry(route, request):
            if request.method != "POST":
                route.continue_()
                return
            payload = request.post_data_json
            if isinstance(payload, dict):
                retry_payload.update(payload)
            route.fulfill(
                status=200,
                headers={"Content-Type": "application/json"},
                body=json.dumps(
                    {
                        "ok": 1,
                        "text": "# Retry Demo\n\n## Methods\nRecovered content after retry.\n",
                        "doc_ir": None,
                    }
                ),
            )

        page.route("**/api/doc/*/save", _on_save)
        page.route("**/api/doc/*/doc_ir/ops", _on_doc_ir_ops)
        page.route("**/api/doc/*/generate/stream", _on_generate)
        page.route("**/api/doc/*/generate/section*", _on_retry)

        _send_assistant(page, "Generate methods section with possible retry.")
        page.wait_for_selector(".section-failures")
        page.wait_for_function("window.__waGetStore && window.__waGetStore('generating') === false")
        with page.expect_request("**/api/doc/*/generate/section", timeout=30000):
            page.evaluate("document.querySelector('.section-failures .btn.ghost')?.click()")
        page.wait_for_function(
            "window.__waGetStore && String(window.__waGetStore('sourceText') || '').includes('Recovered content after retry.')"
        )

        assert retry_payload.get("section") == "Methods"

        context.close()
        browser.close()


def test_upload_text_and_image_files_are_accepted(server_url, tmp_path):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        _open_page(page, server_url)

        txt_path = tmp_path / "upload-notes.txt"
        txt_path.write_text("plain text upload for playwright validation", encoding="utf-8")
        md_path = tmp_path / "upload-brief.md"
        md_path.write_text("# Upload Brief\n\n- item 1\n- item 2\n", encoding="utf-8")
        csv_path = tmp_path / "upload-data.csv"
        csv_path.write_text("name,value\nalpha,1\nbeta,2\n", encoding="utf-8")
        json_path = tmp_path / "upload-config.json"
        json_path.write_text('{"topic":"playwright","mode":"persona"}', encoding="utf-8")
        png_path = tmp_path / "upload-image.png"
        png_path.write_bytes(
            base64.b64decode(
                "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8Xw8AAtMB9p64K6sAAAAASUVORK5CYII="
            )
        )

        file_input = ".assistant-dock input[type='file'][accept*='.docx']"

        with page.expect_response("**/api/doc/*/upload") as txt_resp_info:
            page.set_input_files(file_input, str(txt_path))
        assert txt_resp_info.value.ok

        with page.expect_response("**/api/doc/*/upload") as md_resp_info:
            page.set_input_files(file_input, str(md_path))
        assert md_resp_info.value.ok

        with page.expect_response("**/api/doc/*/upload") as csv_resp_info:
            page.set_input_files(file_input, str(csv_path))
        assert csv_resp_info.value.ok

        with page.expect_response("**/api/doc/*/upload") as json_resp_info:
            page.set_input_files(file_input, str(json_path))
        assert json_resp_info.value.ok

        with page.expect_response("**/api/doc/*/upload") as png_resp_info:
            page.set_input_files(file_input, str(png_path))
        assert png_resp_info.value.ok

        page.wait_for_function(
            """
            () => {
              const chat = document.querySelector('.assistant-dock .chat-history');
              if (!chat) return false;
              const t = chat.innerText || '';
              return t.includes('upload-notes.txt')
                && t.includes('upload-brief.md')
                && t.includes('upload-data.csv')
                && t.includes('upload-config.json')
                && t.includes('upload-image.png');
            }
            """
        )

        context.close()
        browser.close()


def test_intent_inference_for_continue_and_overwrite_without_dialog(server_url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        doc_id = _open_page(page, server_url)
        _seed_doc(
            page,
            doc_id,
            "# Existing\n\n## Intro\nThis existing content is long enough to trigger compose mode logic.",
        )
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector(".assistant-dock textarea")

        payloads: list[dict] = []
        dialogs: list[str] = []
        page.on("dialog", lambda dialog: (dialogs.append(dialog.message), dialog.accept()))

        def _on_generate(route, request):
            if request.method != "POST":
                route.continue_()
                return
            payload = request.post_data_json
            payloads.append(payload if isinstance(payload, dict) else {})
            route.fulfill(
                status=200,
                headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"},
                body='event: final\ndata: {"text":"# Done\\n\\nAll good."}\n\n',
            )

        page.route("**/api/doc/*/generate/stream", _on_generate)

        _send_assistant(page, "\u8bf7\u7eed\u5199\u7b2c\u4e8c\u7ae0\u65b9\u6cd5\u90e8\u5206")
        _wait_until(lambda: len(payloads) >= 1, timeout_s=5)
        page.wait_for_function("window.__waGetStore && window.__waGetStore('generating') === false")

        _send_assistant(page, "\u8bf7\u4ece\u5934\u8986\u76d6\u91cd\u5199\u6574\u7bc7\u6587\u6863")
        _wait_until(lambda: len(payloads) >= 2, timeout_s=5)
        page.wait_for_function("window.__waGetStore && window.__waGetStore('generating') === false")

        _send_assistant(page, "Please continue writing the methods section based on the existing draft.")
        _wait_until(lambda: len(payloads) >= 3, timeout_s=5)
        page.wait_for_function("window.__waGetStore && window.__waGetStore('generating') === false")

        _send_assistant(page, "Please rewrite the entire document from scratch.")
        _wait_until(lambda: len(payloads) >= 4, timeout_s=5)

        assert payloads[0].get("compose_mode") == "continue"
        assert payloads[1].get("compose_mode") == "overwrite"
        assert payloads[2].get("compose_mode") == "continue"
        assert payloads[3].get("compose_mode") == "overwrite"
        assert not dialogs

        context.close()
        browser.close()


def test_modify_intent_prefers_continue_not_overwrite(server_url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        doc_id = _open_page(page, server_url)
        _seed_doc(
            page,
            doc_id,
            "# Draft\n\n## Body\nFirst paragraph.\n\nSecond paragraph for refinement.\n\nConclusion.",
        )
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector(".assistant-dock textarea")
        page.wait_for_function(
            "window.__waGetStore && String(window.__waGetStore('sourceText') || '').includes('Second paragraph for refinement.')"
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
            route.fulfill(
                status=200,
                headers={"Content-Type": "text/event-stream", "Cache-Control": "no-cache"},
                body='event: final\ndata: {"text":"# Draft\\n\\nupdated"}\n\n',
            )

        page.route("**/api/doc/*/generate/stream", _on_generate)

        _send_assistant(page, "Please polish the second paragraph and keep the original meaning.")
        _wait_until(lambda: bool(captured_payload), timeout_s=5)

        req_instruction = str(captured_payload.get("instruction") or "")
        assert captured_payload.get("compose_mode") == "continue"
        assert "\u4fdd\u7559\u73b0\u6709\u5185\u5bb9\u7ed3\u6784" in req_instruction
        assert "\u5ffd\u7565\u5f53\u524d\u5df2\u6709\u6b63\u6587" not in req_instruction
        assert dialogs

        context.close()
        browser.close()


def test_component_multi_select_and_ctrl_enter_opens_inline_panel(server_url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        doc_id = _open_page(page, server_url)
        _seed_doc(
            page,
            doc_id,
            "# Component\n\n## Section Alpha\nParagraph one.\n\nParagraph two.\n",
        )
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector(".editable [data-section-id]")
        page.wait_for_selector(".editable p[data-block-id]")

        page.locator(".editable [data-section-id]").first.click(modifiers=["Alt"])
        page.locator(".editable p[data-block-id]").first.click(modifiers=["Control"])
        page.wait_for_selector(".inline-selection-bar")
        assert "2" in page.inner_text(".inline-selection-bar")

        page.keyboard.press("Control+Enter")
        page.wait_for_selector(".inline-edit-popover")
        assert page.locator(".inline-edit-popover .selected-chip").count() >= 2

        context.close()
        browser.close()


def test_component_inline_style_panel_changes_font_and_size(server_url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        doc_id = _open_page(page, server_url)
        _seed_doc(page, doc_id, "# Style\n\n## Intro\nParagraph for style panel test.")
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector(".editable p[data-block-id]")

        page.locator(".editable p[data-block-id]").first.click(modifiers=["Alt"])
        page.wait_for_selector(".inline-selection-bar")
        page.click(".inline-selection-bar .mini-btn:nth-of-type(2)")
        page.wait_for_selector(".inline-edit-popover")

        font_value = page.eval_on_selector(
            ".inline-style-row select:nth-of-type(1)",
            "el => { const opts = Array.from(el.options).map(o => String(o.value || '').trim()).filter(Boolean); return opts[0] || null; }",
        )
        assert font_value
        page.select_option(".inline-style-row select:nth-of-type(1)", str(font_value))
        page.dispatch_event(".inline-style-row select:nth-of-type(1)", "change")

        size_value = page.eval_on_selector(
            ".inline-style-row select:nth-of-type(2)",
            "el => { const opts = Array.from(el.options).map(o => String(o.value || '').trim()).filter(Boolean); return opts.find(v => v.includes('20')) || opts[0] || null; }",
        )
        assert size_value
        page.select_option(".inline-style-row select:nth-of-type(2)", str(size_value))
        page.dispatch_event(".inline-style-row select:nth-of-type(2)", "change")
        page.wait_for_timeout(200)

        style_attr = page.get_attribute(".editable p[data-block-id]", "style") or ""
        assert "font-family" in style_attr.lower()
        assert "font-size:" in style_attr.replace(" ", "").lower()

        context.close()
        browser.close()


def test_document_quality_heading_alignment_and_font_contrast(server_url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        doc_id = _open_page(page, server_url)
        source_text = (
            "# Quality Report\n\n"
            "## Table of Contents\n"
            "- Background\n"
            "- References\n\n"
            "## Background\n"
            "This paragraph includes citation [1].\n\n"
            "## References\n"
            "[1] Smith J. Example reference. 2024.\n"
        )
        _seed_doc(page, doc_id, source_text)
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector(".editable h2")
        page.wait_for_selector(".editable p")

        style_snapshot = page.evaluate(
            """
            () => {
              const h2 = document.querySelector('.editable h2');
              const p = document.querySelector('.editable p');
              const root = document.querySelector('.editable');
              if (!h2 || !p || !root) return null;
              const hs = getComputedStyle(h2);
              const ps = getComputedStyle(p);
              return {
                align: hs.textAlign || '',
                h2Size: parseFloat(hs.fontSize || '0'),
                pSize: parseFloat(ps.fontSize || '0'),
                rawText: root.innerText || ''
              };
            }
            """
        )
        assert style_snapshot is not None
        assert str(style_snapshot.get("align") or "").lower() == "center"
        assert float(style_snapshot.get("h2Size") or 0) > float(style_snapshot.get("pSize") or 0)
        raw_text = str(style_snapshot.get("rawText") or "")
        assert "Table of Contents" in raw_text
        assert "References" in raw_text
        assert "[1]" in raw_text

        context.close()
        browser.close()


def test_document_quality_citation_verify_pipeline(server_url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        doc_id = _open_page(page, server_url)

        page.evaluate(
            """
            async ({ docId }) => {
              await fetch(`/api/doc/${docId}/citations`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  items: [
                    { id: 'smith2024', author: 'John Smith', title: 'Large Language Model Evaluation in Practice', year: '2024', source: 'https://example.org/paper' },
                    { id: 'unknown2020', author: 'Unknown', title: 'Totally Unknown Paper', year: '2020', source: '' }
                  ]
                })
              })
            }
            """,
            {"docId": doc_id},
        )
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector(".app")

        captured_verify_payload: dict = {}

        def _on_verify(route, request):
            if request.method != "POST":
                route.continue_()
                return
            payload = request.post_data_json
            if isinstance(payload, dict):
                captured_verify_payload.update(payload)
            body = {
                "ok": 1,
                "items": [
                    {
                        "id": "smith2024",
                        "status": "verified",
                        "provider": "crossref",
                        "score": 0.93,
                        "matched_title": "Large Language Model Evaluation in Practice",
                        "matched_year": "2024",
                        "matched_source": "Journal of LLM Studies",
                    },
                    {
                        "id": "unknown2020",
                        "status": "not_found",
                        "provider": "",
                        "score": 0.1,
                        "matched_title": "",
                        "matched_year": "",
                        "matched_source": "",
                    },
                ],
                "updated_items": [
                    {
                        "id": "smith2024",
                        "author": "John Smith",
                        "title": "Large Language Model Evaluation in Practice",
                        "year": "2024",
                        "source": "Journal of LLM Studies",
                    },
                    {
                        "id": "unknown2020",
                        "author": "Unknown",
                        "title": "Totally Unknown Paper",
                        "year": "2020",
                        "source": "",
                    },
                ],
                "summary": {"total": 2, "verified": 1, "possible": 0, "not_found": 1, "error": 0},
            }
            route.fulfill(
                status=200,
                headers={"Content-Type": "application/json"},
                body=json.dumps(body),
            )

        page.route("**/api/doc/*/citations/verify", _on_verify)

        page.click(".nav-btn[title='引用']")
        page.wait_for_selector(".modal h2")
        page.wait_for_selector(".list-section .citation-item")

        page.click(".btn-verify")
        page.wait_for_selector(".verify-summary")
        page.wait_for_selector(".status.ok")

        summary_text = page.inner_text(".verify-summary")
        assert "总计 2" in summary_text
        assert "已核验 1" in summary_text
        assert "未命中 1" in summary_text
        assert captured_verify_payload.get("persist") is True
        assert isinstance(captured_verify_payload.get("items"), list)
        assert "匹配标题" in page.inner_text(".citation-item")

        context.close()
        browser.close()


def test_document_quality_export_block_opens_citation_modal(server_url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        doc_id = _open_page(page, server_url)
        _seed_doc(page, doc_id, "# Export Gate\n\n## Intro\nNeed citation [@smith2024].")
        page.evaluate(
            """
            async ({ docId }) => {
              await fetch(`/api/doc/${docId}/citations`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  items: [
                    { id: 'smith2024', author: 'John Smith', title: 'Reliable Citation Checks', year: '2024', source: 'https://example.org/paper' }
                  ]
                })
              })
            }
            """,
            {"docId": doc_id},
        )
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector(".app")

        download_called = {"v": False}

        def _on_export_check(route, request):
            if request.method != "GET":
                route.continue_()
                return
            body = {
                "ok": 1,
                "format": "docx",
                "can_export": False,
                "issues": [
                    {
                        "code": "citation_unverified",
                        "message": "文档中存在未核验通过的引用，导出已阻止。",
                        "blocking": True,
                    }
                ],
                "warnings": [],
            }
            route.fulfill(
                status=200,
                headers={"Content-Type": "application/json"},
                body=json.dumps(body),
            )

        def _on_download(route, request):
            download_called["v"] = True
            route.fulfill(status=500, body="should not be called when export is blocked")

        page.route("**/api/doc/*/export/check*", _on_export_check)
        page.route("**/download/*.docx", _on_download)

        page.click("button:has-text('导出 Word')")
        page.wait_for_selector(".modal h2")
        page.wait_for_selector(".btn-verify")
        page.wait_for_selector(".toast.bad")

        toast_text = page.inner_text(".toast.bad")
        assert "已自动打开“引用”面板" in toast_text
        assert not download_called["v"]

        context.close()
        browser.close()


def test_component_slash_menu_should_appear_after_slash(server_url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        doc_id = _open_page(page, server_url)
        _seed_doc(page, doc_id, "# Slash\n\n## Intro\nabc")
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector(".editable p[data-block-id]")
        page.click(".editable p[data-block-id]")
        page.keyboard.type("/")
        page.wait_for_selector(".slash-menu", timeout=2000)
        assert page.locator(".slash-menu .slash-item").count() >= 8

        page.keyboard.type("toc")
        page.keyboard.press("Enter")
        page.wait_for_timeout(150)
        assert page.locator(".editable .toc-section").count() >= 1

        page.click(".editable .toc-section")
        page.keyboard.type("/")
        page.wait_for_selector(".slash-menu", timeout=2000)
        page.keyboard.press("Escape")
        page.wait_for_timeout(100)
        assert page.locator(".slash-menu").count() == 0

        context.close()
        browser.close()


def test_component_ctrl_enter_should_create_new_block_plain_enter_newline(server_url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        doc_id = _open_page(page, server_url)
        _seed_doc(page, doc_id, "# Keyboard\n\n## Intro\nabc")
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector(".editable p[data-block-id]")

        para = page.locator(".editable p[data-block-id]").first
        para.click()
        page.keyboard.press("End")
        before = page.locator(".editable [data-block-id]").count()

        page.keyboard.press("Enter")
        page.wait_for_timeout(150)
        after_plain_enter = page.locator(".editable [data-block-id]").count()
        assert after_plain_enter == before
        para_text_after_enter = para.inner_text()
        assert "abc" in para_text_after_enter

        para.click()
        page.keyboard.press("End")
        page.keyboard.press("Control+Enter")
        page.wait_for_timeout(150)
        after_ctrl_enter = page.locator(".editable [data-block-id]").count()
        assert after_ctrl_enter == before + 1

        context.close()
        browser.close()

