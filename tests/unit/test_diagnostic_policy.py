import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from writing_agent.diagnostics import append_diagnostic, diagnostic_path, enabled, write_compact_json
from writing_agent.llm.providers.node_ai_gateway_provider import NodeAIGatewayProvider
from writing_agent.web.domains import revision_edit_common_domain as revision
from writing_agent.web.domains import route_graph_metrics_domain as route


class DiagnosticPolicyTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, {}, clear=True)
        env.start()
        self.addCleanup(env.stop)

    def test_default_off_and_explicit_override(self):
        self.assertFalse(enabled('FEATURE'))
        os.environ['WRITING_AGENT_PERSIST_DIAGNOSTICS'] = '1'
        self.assertTrue(enabled('FEATURE'))
        os.environ['FEATURE'] = '0'
        self.assertFalse(enabled('FEATURE'))
        os.environ['FEATURE'] = 'typo'
        self.assertFalse(enabled('FEATURE'))

    def test_default_paths_respect_data_directory(self):
        os.environ['WRITING_AGENT_DATA_DIR'] = 'custom-data'
        self.assertEqual(route.route_graph_metrics_path(), Path('custom-data/metrics/route_graph_events.jsonl'))
        self.assertEqual(revision._edit_plan_metrics_path(), Path('custom-data/metrics/edit_plan_events.jsonl'))
        self.assertEqual(revision._selected_revision_metrics_path(), Path('custom-data/metrics/selected_revision_events.jsonl'))
        os.environ['PATH_OVERRIDE'] = 'chosen.jsonl'
        self.assertEqual(diagnostic_path('PATH_OVERRIDE', 'unused'), Path('chosen.jsonl'))

    def emit_all(self):
        route.record_route_graph_metric('done', phase='draft', path='test')
        revision._record_edit_plan_metric('done', raw='rewrite', prefer_model=False, fallback_used=False)
        revision._record_selected_revision_metric('done', instruction='rewrite')
        NodeAIGatewayProvider._record_fallback_event(None, reason='unavailable')

    def test_repeated_default_operations_create_nothing(self):
        with tempfile.TemporaryDirectory() as folder:
            os.environ['WRITING_AGENT_DATA_DIR'] = str(Path(folder) / 'data')
            for _ in range(500):
                self.emit_all()
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_opt_in_keeps_all_four_diagnostics(self):
        with tempfile.TemporaryDirectory() as folder:
            os.environ['WRITING_AGENT_DATA_DIR'] = folder
            os.environ['WRITING_AGENT_PERSIST_DIAGNOSTICS'] = '1'
            self.emit_all()
            files = list((Path(folder) / 'metrics').glob('*.jsonl'))
            self.assertEqual(len(files), 4)
            for file in files:
                self.assertIsInstance(json.loads(file.read_text(encoding='utf-8')), dict)

    def test_repeated_writes_bounded_and_valid_utf8(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'events.jsonl'
            for i in range(200):
                self.assertTrue(append_diagnostic(path, {'i': i, 'text': '中文' * 10}, max_bytes=512))
                self.assertLessEqual(path.stat().st_size, 512)
            rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
            self.assertEqual(rows[-1]['i'], 199)
            self.assertFalse(list(Path(folder).glob('*.tmp')))

    def test_oversized_row_does_not_create_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'events.jsonl'
            self.assertFalse(append_diagnostic(path, {'text': 'x' * 500}, max_bytes=100))
            self.assertFalse(path.exists())

    def test_partial_legacy_row_is_not_joined_to_new_json(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'events.jsonl'
            path.write_bytes(b'{"old":1}\n{"interrupted":')
            self.assertTrue(append_diagnostic(path, {'new': 2}, max_bytes=100))
            self.assertEqual([json.loads(line) for line in path.read_text().splitlines()], [{'old': 1}, {'new': 2}])

    def test_atomic_replace_failure_preserves_old_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'events.jsonl'
            path.write_bytes(b'{"old":1}\n' * 100)
            original = path.read_bytes()
            with patch('writing_agent.diagnostics.os.replace', side_effect=PermissionError('busy')):
                self.assertFalse(append_diagnostic(path, {'new': 1}, max_bytes=100))
            self.assertEqual(path.read_bytes(), original)
            self.assertFalse(list(Path(folder).glob('*.tmp')))

    def test_unwritable_log_does_not_break_fallback(self):
        os.environ['WRITING_AGENT_PERSIST_DIAGNOSTICS'] = '1'
        with patch.object(Path, 'mkdir', side_effect=PermissionError('denied')):
            self.emit_all()

    def test_same_process_concurrent_writes_remain_valid(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'events.jsonl'
            with ThreadPoolExecutor(max_workers=4) as pool:
                results = list(pool.map(lambda i: append_diagnostic(path, {'i': i}, max_bytes=256), range(100)))
            self.assertTrue(all(results))
            self.assertLessEqual(path.stat().st_size, 256)
            self.assertTrue(all(isinstance(json.loads(line), dict) for line in path.read_text().splitlines()))

    def test_compact_json_write_is_atomic_and_cleans_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'state.json'
            self.assertTrue(write_compact_json(path, {'中文': [1, 2]}))
            self.assertNotIn('\n', path.read_text(encoding='utf-8'))
            original = path.read_bytes()
            with patch('writing_agent.diagnostics.os.replace', side_effect=PermissionError('busy')):
                self.assertFalse(write_compact_json(path, {'changed': True}))
            self.assertEqual(path.read_bytes(), original)
            self.assertFalse(list(Path(folder).glob('*.tmp')))

    def test_unserializable_json_state_does_not_create_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'state.json'
            self.assertFalse(write_compact_json(path, object()))
            self.assertFalse(path.exists())


if __name__ == '__main__':
    unittest.main()
