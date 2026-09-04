import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from writing_agent.v2 import graph_reference_fallback_domain as cache


class ReferenceCachePolicyTests(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, {}, clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.data = Path(folder.name) / "data"
        os.environ["WRITING_AGENT_DATA_DIR"] = str(self.data)

    def test_cache_lookup_miss_does_not_create_directory(self):
        self.assertEqual(cache._load_cached_reference_sources("missing"), [])
        self.assertFalse(self.data.exists())

    def test_save_is_compact_atomic_and_roundtrips(self):
        cache._save_cached_reference_sources("中文 query", [{"title": "资料"}])
        path = cache._reference_cache_path("中文 query")
        self.assertTrue(path.exists())
        self.assertNotIn("\n", path.read_text(encoding="utf-8"))
        self.assertEqual(cache._load_cached_reference_sources("中文 query"), [{"title": "资料"}])
        self.assertFalse(list(path.parent.glob("*.tmp")))

    def test_expired_and_excess_entries_are_pruned(self):
        os.environ["WRITING_AGENT_REFERENCE_CACHE_MAX_ENTRIES"] = "8"
        root = cache._reference_cache_dir()
        root.mkdir(parents=True)
        expired = root / "expired.json"
        expired.write_text("{}")
        old = time.time() - 400
        os.utime(expired, (old, old))
        os.environ["WRITING_AGENT_REFERENCE_CACHE_TTL_S"] = "300"
        for i in range(12):
            path = root / f"{i:02d}.json"
            path.write_text(json.dumps({"i": i}))
            os.utime(path, (old + i + 350, old + i + 350))
        cache._prune_reference_cache(root)
        self.assertFalse(expired.exists())
        self.assertEqual(len(list(root.glob("*.json"))), 8)

    def test_replace_failure_preserves_previous_value_and_cleans_temp(self):
        cache._save_cached_reference_sources("query", [{"value": "old"}])
        path = cache._reference_cache_path("query")
        before = path.read_bytes()
        with patch("writing_agent.v2.graph_reference_fallback_domain.os.replace", side_effect=PermissionError("busy")):
            cache._save_cached_reference_sources("query", [{"value": "new"}])
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse(list(path.parent.glob("*.tmp")))

    def test_symlink_cache_root_is_not_written_or_pruned(self):
        with patch.object(Path, "is_symlink", return_value=True):
            cache._save_cached_reference_sources("query", [{"value": 1}])
            cache._prune_reference_cache(self.data)
        self.assertFalse(self.data.exists())

    def test_invalid_limits_fall_back_without_breaking_retrieval(self):
        for name in ["WRITING_AGENT_REFERENCE_CACHE_TTL_S", "WRITING_AGENT_REFERENCE_CACHE_MAX_ENTRIES",
                     "WRITING_AGENT_REFERENCE_CACHE_MAX_BYTES", "WRITING_AGENT_REFERENCE_CACHE_ROWS"]:
            os.environ[name] = "invalid"
        cache._save_cached_reference_sources("query", [{"value": 1}])
        self.assertEqual(cache._load_cached_reference_sources("query"), [{"value": 1}])


if __name__ == "__main__":
    unittest.main()
