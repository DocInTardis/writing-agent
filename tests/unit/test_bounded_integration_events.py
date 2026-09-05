from __future__ import annotations

import os
import tempfile
from pathlib import Path

from writing_agent.web.contracts import WebhookEvent
from writing_agent.web.services.integration_service import IntegrationService


def _event(index: int, *, tenant: str = "t1") -> WebhookEvent:
    return WebhookEvent(
        event_type="generation.completed",
        tenant_id=tenant,
        payload={"index": index, "text": "x" * 80},
    )


def test_default_event_path_follows_application_data_directory() -> None:
    previous = os.environ.get("WRITING_AGENT_DATA_DIR")
    try:
        with tempfile.TemporaryDirectory() as root:
            os.environ["WRITING_AGENT_DATA_DIR"] = root
            service = IntegrationService(max_bytes=1024)
            assert service.list_events()["items"] == []
            assert not (Path(root) / "integration").exists()
            service.publish_event(_event(1))
            assert (Path(root) / "integration" / "event_bus.jsonl").exists()
    finally:
        if previous is None:
            os.environ.pop("WRITING_AGENT_DATA_DIR", None)
        else:
            os.environ["WRITING_AGENT_DATA_DIR"] = previous


def test_event_log_is_bounded_and_lists_newest_complete_rows() -> None:
    with tempfile.TemporaryDirectory() as root:
        path = Path(root) / "events.jsonl"
        service = IntegrationService(event_log=path, max_bytes=1100)
        for index in range(30):
            service.publish_event(_event(index))

        assert path.stat().st_size <= 1100
        rows = service.list_events(limit=50)["items"]
        assert rows
        assert rows[-1]["payload"]["index"] == 29
        assert all(row["payload"]["index"] != 0 for row in rows)


def test_event_listing_filters_tenant_without_loading_unbounded_history() -> None:
    with tempfile.TemporaryDirectory() as root:
        service = IntegrationService(event_log=Path(root) / "events.jsonl", max_bytes=4096)
        service.publish_event(_event(1, tenant="t1"))
        service.publish_event(_event(2, tenant="t2"))

        rows = service.list_events(limit=10, tenant_id="t2")["items"]
        assert [row["payload"]["index"] for row in rows] == [2]
