from __future__ import annotations

import hashlib
import hmac
import json
import os
import tempfile
import time
from pathlib import Path

from writing_agent.bounded_jsonl import read_recent_jsonl
from writing_agent.web.services.audit_service import AuditService


def _expected_hash(row: dict) -> str:
    body = {key: value for key, value in row.items() if key not in {"hash", "signature"}}
    payload = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_audit_default_path_follows_data_directory_without_eager_write() -> None:
    previous = os.environ.get("WRITING_AGENT_DATA_DIR")
    try:
        with tempfile.TemporaryDirectory() as root:
            os.environ["WRITING_AGENT_DATA_DIR"] = root
            service = AuditService()
            assert service._last_hash() == ""
            assert not (Path(root) / "audit").exists()
            service.append(actor="owner", action="save", tenant_id="default", payload={})
            assert (Path(root) / "audit" / "app_audit_chain.ndjson").exists()
    finally:
        if previous is None:
            os.environ.pop("WRITING_AGENT_DATA_DIR", None)
        else:
            os.environ["WRITING_AGENT_DATA_DIR"] = previous


def test_audit_rotation_is_bounded_and_starts_with_explicit_anchor() -> None:
    with tempfile.TemporaryDirectory() as root:
        path = Path(root) / "audit.ndjson"
        service = AuditService(path=path, max_bytes=1400)
        for index in range(30):
            service.append(
                actor="owner",
                action="save",
                tenant_id="default",
                payload={"index": index, "detail": "x" * 80},
            )

        assert path.stat().st_size <= 1400
        rows = read_recent_jsonl(path, max_bytes=1400)
        assert rows[0]["action"] == "audit_window_rotated"
        assert rows[0]["payload"]["prior_terminal_hash"]
        assert rows[0]["prev_hash"] == ""
        assert rows[-1]["payload"]["index"] == 29
        for index, row in enumerate(rows):
            assert row["hash"] == _expected_hash(row)
            if index:
                assert row["prev_hash"] == rows[index - 1]["hash"]


def test_audit_signatures_remain_valid_after_rotation() -> None:
    with tempfile.TemporaryDirectory() as root:
        path = Path(root) / "audit.ndjson"
        service = AuditService(path=path, secret="secret", max_bytes=900)
        for index in range(10):
            service.append(actor="owner", action="save", tenant_id="default", payload={"index": index})

        for row in read_recent_jsonl(path, max_bytes=900):
            expected = hmac.new(b"secret", row["hash"].encode("utf-8"), hashlib.sha256).hexdigest()
            assert hmac.compare_digest(row["signature"], expected)


def test_expired_audit_window_rotates_with_terminal_anchor() -> None:
    with tempfile.TemporaryDirectory() as root:
        path = Path(root) / "audit.ndjson"
        service = AuditService(path=path, max_bytes=4096, max_age_s=60)
        first = service.append(actor="owner", action="old", tenant_id="default", payload={})
        rows = read_recent_jsonl(path, max_bytes=4096)
        rows[0]["ts"] = time.time() - 1000
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

        current = service.append(actor="owner", action="current", tenant_id="default", payload={})

        rotated = read_recent_jsonl(path, max_bytes=4096)
        assert [row["action"] for row in rotated] == ["audit_window_rotated", "current"]
        assert rotated[0]["payload"]["prior_terminal_hash"] == first["hash"]
        assert current["prev_hash"] == rotated[0]["hash"]
