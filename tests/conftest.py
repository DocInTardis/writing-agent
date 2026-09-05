"""Shared test isolation for user-owned runtime data."""

import pytest


@pytest.fixture(autouse=True)
def _isolate_runtime_data(tmp_path, monkeypatch):
    data_dir = tmp_path / "runtime-data"
    monkeypatch.setenv("WRITING_AGENT_DATA_DIR", str(data_dir))
    from writing_agent.llm.user_config import UserConfigStore

    store = UserConfigStore()
    store._config_path = data_dir / "user_llm_configs.json"
    store._cached_config = None
    store._cached_at = 0.0
    yield
    store._cached_config = None
    store._cached_at = 0.0
