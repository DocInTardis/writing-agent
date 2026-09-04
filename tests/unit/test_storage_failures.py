"""Persistence failure contracts. All writes are confined to temporary fixtures."""
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from writing_agent.storage import DocSession, InMemoryStore


class StorageFailureTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = Path(self.folder.name)
        self.store = InMemoryStore(self.root, max_sessions=1)
        self.original = self.store.create()
        self.original.doc_text = '保留原文'
        self.store.put(self.original)
        self.file = self.root / (self.original.id + '.json')

    def test_replace_failure_preserves_old_file_and_cached_object(self):
        before = self.file.read_bytes()
        changed = deepcopy(self.original)
        changed.doc_text = 'new'
        with patch.object(self.store, '_replace_session_file', side_effect=PermissionError('locked')):
            with self.assertRaises(PermissionError):
                self.store.put(changed)
        self.assertIs(self.store.get(self.original.id), self.original)
        self.assertEqual(self.file.read_bytes(), before)
        self.assertEqual(list(self.root.glob('*.tmp')), [])

    def test_failed_new_save_does_not_evict_existing_document(self):
        with patch.object(self.store, '_persist_session', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.store.put(DocSession(id='new-document'))
        self.assertIsNotNone(self.store.get(self.original.id))
        self.assertIsNone(self.store.get('new-document'))

    def test_failed_create_does_not_publish_or_evict(self):
        before = self.store.items()
        with patch.object(self.store, '_persist_session', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.store.create()
        self.assertEqual(self.store.items(), before)

    def test_failed_delete_keeps_memory_and_file(self):
        with patch.object(Path, 'unlink', side_effect=PermissionError('locked')):
            with self.assertRaises(PermissionError):
                self.store.delete(self.original.id)
        self.assertIsNotNone(self.store.get(self.original.id))
        self.assertTrue(self.file.exists())

    def test_compact_json_roundtrip_preserves_document(self):
        payload = self.file.read_text(encoding='utf-8')
        self.assertNotIn('\n', payload)
        self.assertEqual(json.loads(payload)['doc_text'], '保留原文')
        restored = InMemoryStore(self.root)
        self.assertEqual(restored.get(self.original.id).doc_text, '保留原文')

    def test_temporary_names_are_unique_and_cleaned(self):
        temporary_names = []
        original_replace = self.store._replace_session_file

        def record(source, destination):
            temporary_names.append(source.name)
            original_replace(source, destination)

        with patch.object(self.store, '_replace_session_file', side_effect=record):
            self.store.put(self.original)
            self.store.put(self.original)
        self.assertEqual(len(set(temporary_names)), 2)
        self.assertEqual(list(self.root.glob('*.tmp')), [])

    def test_successful_delete_removes_both_copies(self):
        self.assertTrue(self.store.delete(self.original.id))
        self.assertIsNone(self.store.get(self.original.id))
        self.assertFalse(self.file.exists())


if __name__ == '__main__':
    unittest.main()
