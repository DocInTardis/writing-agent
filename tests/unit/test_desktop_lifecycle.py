"""Headless contracts for the system-WebView desktop shell."""
import ast
import importlib.util
import io
import os
import sys
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from writing_agent import launch

ROOT = Path(__file__).resolve().parents[2]


def load_desktop():
    webview = SimpleNamespace(settings={}, create_window=Mock(), start=Mock())
    spec = importlib.util.spec_from_file_location("_desktop_contract_test", ROOT / "writing_agent/desktop_app.py")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"webview": webview}):
        spec.loader.exec_module(module)
    return module, webview


class DesktopLifecycleTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)
        previous_bytecode = sys.dont_write_bytecode
        self.addCleanup(setattr, sys, "dont_write_bytecode", previous_bytecode)
        self.desktop, self.webview = load_desktop()

    def test_ready_loads_workbench_once(self):
        window = Mock()
        server = Mock()
        server.server.started = True
        self.desktop._load_when_ready(window, server, "http://127.0.0.1:8000/")
        window.load_url.assert_called_once_with("http://127.0.0.1:8000/")
        window.load_html.assert_not_called()

    def test_failed_server_stops_and_shows_error(self):
        window = Mock()
        server = Mock()
        server.server.started = False
        server.is_alive.return_value = False
        self.desktop._load_when_ready(window, server, "http://test/")
        server.stop.assert_called_once()
        window.load_html.assert_called_once()

    def test_timeout_stops_without_reload_loop(self):
        window = Mock()
        server = Mock()
        server.server.started = False
        server.is_alive.return_value = True
        with patch.object(self.desktop.time, "monotonic", side_effect=[0.0, 31.0]):
            self.desktop._load_when_ready(window, server, "http://test/", timeout_s=30)
        server.stop.assert_called_once()
        window.load_url.assert_not_called()
        window.load_html.assert_called_once()

    def test_main_uses_private_system_webview_and_allows_downloads(self):
        class _Event:
            def __iadd__(self, callback):
                self.callback = callback
                return self

        closed = _Event()
        window = SimpleNamespace(events=SimpleNamespace(closed=closed))
        self.webview.create_window.return_value = window
        worker = Mock()
        worker.is_alive.return_value = False
        with patch.object(self.desktop, "_pick_port", return_value=8123), patch.object(
            self.desktop, "UvicornWorker", return_value=worker
        ):
            self.assertEqual(self.desktop.main([]), 0)
        self.assertTrue(self.webview.settings["ALLOW_DOWNLOADS"])
        self.assertEqual(self.webview.start.call_args.kwargs["gui"], "edgechromium")
        self.assertTrue(self.webview.start.call_args.kwargs["private_mode"])
        worker.start.assert_called_once()
        worker.stop.assert_called()
        worker.join.assert_called_once_with(timeout=5)

    def test_default_launcher_uses_desktop(self):
        entry = Mock(return_value=0)
        with patch.dict(sys.modules, {"writing_agent.desktop_app": SimpleNamespace(main=entry)}):
            self.assertEqual(launch.main([]), 0)
        entry.assert_called_once_with([])

    def test_missing_desktop_dependency_does_not_fall_back(self):
        original_import = __import__

        def missing(name, *args, **kwargs):
            if name == "writing_agent.desktop_app":
                raise ModuleNotFoundError("missing webview", name="webview")
            return original_import(name, *args, **kwargs)

        output = io.StringIO()
        with patch("builtins.__import__", side_effect=missing), redirect_stderr(output):
            self.assertEqual(launch.main([]), 2)
        self.assertIn("start_desktop.ps1", output.getvalue())

    def test_web_mode_is_explicit_and_does_not_bootstrap_models(self):
        with patch("uvicorn.run") as run, patch.object(launch, "_pick_available_port", return_value=8123):
            self.assertEqual(launch.main(["--web"]), 0)
        self.assertEqual(run.call_args.kwargs["port"], 8123)

    def test_launch_sources_cannot_start_or_download_models(self):
        for filename in ["launch.py", "desktop_app.py"]:
            source = (ROOT / "writing_agent" / filename).read_text(encoding="utf-8")
            for forbidden in ["pull_model(", "get_default_provider(", "subprocess.Popen(", "time.sleep("]:
                self.assertNotIn(forbidden, source)

    def test_service_lifespan_does_not_warm_models(self):
        source = (ROOT / "writing_agent/web/app_v2.py").read_text(encoding="utf-8-sig")
        self.assertNotIn("_startup_warm_models", source)
        tree = ast.parse(source)
        lifespan = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "_app_lifespan")
        for node in ast.walk(lifespan):
            if isinstance(node, ast.Name):
                self.assertNotIn(node.id, {"OllamaClient", "get_default_provider", "get_ollama_settings"})


if __name__ == "__main__":
    unittest.main()
