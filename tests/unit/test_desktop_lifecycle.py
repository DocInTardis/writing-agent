"""Desktop orchestration contracts, without installing a second browser runtime.

Qt objects are test doubles. These tests do not claim to validate real rendering.
"""
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
    qt = SimpleNamespace(
        QtCore=SimpleNamespace(QTimer=SimpleNamespace(singleShot=Mock()), QUrl=lambda url: url),
        QtGui=SimpleNamespace(),
        QtWidgets=SimpleNamespace(QMainWindow=object, QFileDialog=SimpleNamespace(getSaveFileName=Mock())),
    )
    modules = {
        'PySide6': qt,
        'PySide6.QtWebEngineCore': SimpleNamespace(QWebEngineProfile=object, QWebEngineSettings=object),
        'PySide6.QtWebEngineWidgets': SimpleNamespace(QWebEngineView=object),
    }
    spec = importlib.util.spec_from_file_location('_desktop_contract_test', ROOT / 'writing_agent/desktop_app.py')
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules):
        spec.loader.exec_module(module)
    return module


class DesktopLifecycleTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ)
        environment.start()
        self.addCleanup(environment.stop)
        previous_bytecode = sys.dont_write_bytecode
        self.addCleanup(setattr, sys, 'dont_write_bytecode', previous_bytecode)
        self.desktop = load_desktop()
        self.window = self.desktop.MainWindow.__new__(self.desktop.MainWindow)
        self.window._closing = False
        self.window._load_started = False
        self.window._startup_deadline = float('inf')
        self.window._url = 'http://127.0.0.1:8000/'
        self.window._server = Mock()
        self.window._server.server.started = False
        self.window._server.is_alive.return_value = True
        self.window.view = Mock()

    def test_ready_loads_once(self):
        self.window._server.server.started = True
        self.window._schedule_ready_check()
        self.window._schedule_ready_check()
        self.window.view.setUrl.assert_called_once_with(self.window._url)

    def test_starting_schedules_without_network_wait(self):
        self.window._schedule_ready_check()
        self.desktop.QtCore.QTimer.singleShot.assert_called_once()
        self.window.view.setUrl.assert_not_called()

    def test_timeout_stops_without_retry_loop(self):
        self.window._startup_deadline = 0
        self.window._schedule_ready_check()
        self.window._server.stop.assert_called_once()
        self.window.view.setHtml.assert_called_once()
        self.desktop.QtCore.QTimer.singleShot.assert_not_called()

    def test_failed_server_does_not_retry(self):
        self.window._server.is_alive.return_value = False
        self.window._schedule_ready_check()
        self.window.view.setHtml.assert_called_once()
        self.desktop.QtCore.QTimer.singleShot.assert_not_called()

    def test_load_failure_does_not_reload_error_page(self):
        self.window._load_started = True
        self.window._on_load_finished(False)
        self.window._on_load_finished(True)
        self.window.view.setHtml.assert_called_once()
        self.window.view.reload.assert_not_called()
        self.desktop.QtCore.QTimer.singleShot.assert_not_called()

    def test_closed_window_does_not_schedule(self):
        self.window._closing = True
        self.window._schedule_ready_check()
        self.desktop.QtCore.QTimer.singleShot.assert_not_called()

    def test_manual_retry_navigates_back_to_workbench(self):
        self.window._reload_workbench()
        self.window.view.setUrl.assert_called_once_with(self.window._url)

    def test_download_uses_qt6_directory_and_filename(self):
        target = ROOT / 'example.docx'
        self.desktop.QtWidgets.QFileDialog.getSaveFileName.return_value = (str(target), '')
        download = Mock(spec=['downloadFileName', 'setDownloadDirectory', 'setDownloadFileName', 'accept', 'cancel'])
        download.downloadFileName.return_value = 'example.docx'
        self.window._handle_download(download)
        download.setDownloadDirectory.assert_called_once_with(str(target.parent))
        download.setDownloadFileName.assert_called_once_with(target.name)
        download.accept.assert_called_once()

    def test_cancelled_download_is_not_written(self):
        self.desktop.QtWidgets.QFileDialog.getSaveFileName.return_value = ('', '')
        download = Mock()
        self.window._handle_download(download)
        download.cancel.assert_called_once()
        download.accept.assert_not_called()

    def test_default_launcher_uses_desktop(self):
        entry = Mock(return_value=0)
        with patch.dict(sys.modules, {'writing_agent.desktop_app': SimpleNamespace(main=entry)}):
            self.assertEqual(launch.main([]), 0)
        entry.assert_called_once_with([])

    def test_missing_desktop_dependency_does_not_fall_back(self):
        original_import = __import__

        def missing(name, *args, **kwargs):
            if name == 'writing_agent.desktop_app':
                raise ModuleNotFoundError("missing PySide6", name='PySide6')
            return original_import(name, *args, **kwargs)

        output = io.StringIO()
        with patch('builtins.__import__', side_effect=missing), redirect_stderr(output):
            self.assertEqual(launch.main([]), 2)
        self.assertIn('start_desktop.ps1', output.getvalue())

    def test_web_mode_is_explicit_and_does_not_bootstrap_models(self):
        with patch('uvicorn.run') as run, patch.object(launch, '_pick_available_port', return_value=8123):
            self.assertEqual(launch.main(['--web']), 0)
        self.assertEqual(run.call_args.kwargs['port'], 8123)

    def test_launch_sources_cannot_start_or_download_models(self):
        for filename in ['launch.py', 'desktop_app.py']:
            source = (ROOT / 'writing_agent' / filename).read_text(encoding='utf-8')
            for forbidden in ['pull_model(', 'get_default_provider(', 'subprocess.Popen(', 'time.sleep(']:
                self.assertNotIn(forbidden, source)
        source = (ROOT / 'writing_agent/desktop_app.py').read_text(encoding='utf-8')
        self.assertNotIn('QTWEBENGINE_DISABLE_SANDBOX', source)

    def test_service_lifespan_does_not_warm_models(self):
        source = (ROOT / 'writing_agent/web/app_v2.py').read_text(encoding='utf-8-sig')
        self.assertNotIn('_startup_warm_models', source)
        self.assertNotIn('_warm_ollama_model', source)
        tree = ast.parse(source)
        lifespan = next(node for node in tree.body if isinstance(node, ast.AsyncFunctionDef) and node.name == '_app_lifespan')
        for node in ast.walk(lifespan):
            if isinstance(node, ast.Name):
                self.assertNotIn(node.id, {'OllamaClient', 'get_default_provider', 'get_ollama_settings'})

    def test_event_loop_error_still_stops_and_joins_server(self):
        app = Mock()
        app.exec.side_effect = RuntimeError('event loop failed')
        worker = Mock()
        worker.is_alive.return_value = False
        with patch.object(self.desktop, '_configure_webengine_env'), \
             patch.object(self.desktop, '_pick_port', return_value=8123), \
             patch.object(self.desktop, 'UvicornWorker', return_value=worker), \
             patch.object(self.desktop, 'MainWindow'), \
             patch.object(self.desktop.QtWidgets, 'QApplication', return_value=app, create=True):
            with self.assertRaisesRegex(RuntimeError, 'event loop failed'):
                self.desktop.main([])
        worker.stop.assert_called_once()
        worker.join.assert_called_once_with(timeout=5)


if __name__ == '__main__':
    unittest.main()
