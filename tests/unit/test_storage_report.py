import tempfile
import unittest
import stat
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

from writing_agent.storage_report import classify, inventory


class StorageReportTests(unittest.TestCase):
    def test_data_is_never_classified_as_disposable(self):
        self.assertEqual(classify(('.data', 'cache', 'item.json')), 'user_data_and_runtime_state')
        self.assertEqual(classify(('.data', 'node_modules', 'file')), 'user_data_and_runtime_state')

    def test_inventory_counts_without_changing_files(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / '.data').mkdir()
            doc = root / '.data' / 'document'
            doc.write_bytes(b'keep')
            (root / 'node_modules').mkdir()
            (root / 'node_modules' / 'lib').write_bytes(b'lib')
            before = doc.stat().st_mtime_ns
            report = inventory(root)
            self.assertEqual(report['total_bytes'], 7)
            self.assertEqual(report['categories']['user_data_and_runtime_state']['bytes'], 4)
            self.assertEqual(doc.stat().st_mtime_ns, before)
            self.assertEqual(doc.read_bytes(), b'keep')
            self.assertEqual(report['errors'], [])

    def test_scan_errors_are_reported_not_hidden_as_zero(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch('writing_agent.storage_report.os.scandir', side_effect=PermissionError('denied')):
                report = inventory(Path(folder))
            self.assertEqual(len(report['errors']), 1)
            self.assertIn('denied', report['errors'][0]['error'])

    def test_missing_root_is_an_error(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(FileNotFoundError):
                inventory(Path(folder) / 'missing')

    def test_reparse_point_is_not_traversed(self):
        entry = SimpleNamespace(name='linked', stat=lambda **_: SimpleNamespace(
            st_mode=stat.S_IFDIR, st_file_attributes=0x400))
        with tempfile.TemporaryDirectory() as folder:
            with patch('writing_agent.storage_report.os.scandir') as scan:
                scan.return_value.__enter__.return_value = iter([entry])
                report = inventory(Path(folder))
                scan.assert_called_once()
        self.assertEqual(report['skipped_links'], ['linked'])
        self.assertEqual(report['total_bytes'], 0)


if __name__ == '__main__':
    unittest.main()
