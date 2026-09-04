import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from writing_agent.web import app_v2


class StreamMetricsPolicyTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / 'metrics' / 'stream.json'
        target = patch.object(app_v2, '_STREAM_METRICS_PATH', self.path)
        target.start()
        self.addCleanup(target.stop)

    def test_normal_streams_do_not_write_metrics(self):
        for _ in range(500):
            app_v2._record_stream_timing(total_s=1, max_gap_s=.1)
        self.assertFalse(self.path.exists())

    def test_opt_in_is_compact_and_keeps_thirty_runs(self):
        os.environ['WRITING_AGENT_PERSIST_DIAGNOSTICS'] = '1'
        for i in range(50):
            app_v2._record_stream_timing(total_s=i, max_gap_s=.1)
        text = self.path.read_text(encoding='utf-8')
        self.assertNotIn('\n', text)
        rows = json.loads(text)['runs']
        self.assertEqual(len(rows), 30)
        self.assertEqual(rows[0]['total_s'], 20)
        self.assertEqual(rows[-1]['total_s'], 49)

    def test_feature_override_wins(self):
        os.environ['WRITING_AGENT_PERSIST_DIAGNOSTICS'] = '1'
        os.environ['WRITING_AGENT_STREAM_TIMING_ENABLE'] = '0'
        app_v2._record_stream_timing(total_s=1, max_gap_s=.1)
        self.assertFalse(self.path.exists())

    def test_write_failure_does_not_fail_generation(self):
        os.environ['WRITING_AGENT_STREAM_TIMING_ENABLE'] = '1'
        with patch.object(app_v2, 'write_compact_json', return_value=False):
            app_v2._record_stream_timing(total_s=1, max_gap_s=.1)


if __name__ == '__main__':
    unittest.main()
