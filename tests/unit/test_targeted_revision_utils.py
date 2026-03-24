from __future__ import annotations

from scripts.targeted_revision_utils import pick_top_risk_sections, run_targeted_section_revisions


class _Resp:
    def __init__(self, status_code: int, payload: dict):
        self.status_code = status_code
        self._payload = payload
        self.content = b"1"
        self.text = str(payload)

    def json(self):
        return self._payload


class _Client:
    def __init__(self):
        self.calls = []

    def post(self, url: str, json: dict):
        self.calls.append((url, dict(json)))
        title = str(json.get("target_section") or "")
        text = str(json.get("text") or "")
        revised = text.replace(f"{title} body.", f"{title} rewritten body.")
        return _Resp(200, {"text": revised, "revision_meta": {"selection_source": "target_section"}})


def test_pick_top_risk_sections_prefers_failed_or_rewritten_rows() -> None:
    snapshot = {
        "section_originality_hot_sample": {
            "rows": [
                {"title": "A", "failed_event_count": 2, "rewrite_count": 1, "retry_count": 0, "latest_passed": True},
                {"title": "B", "failed_event_count": 0, "rewrite_count": 0, "retry_count": 0, "latest_passed": True},
                {"title": "C", "failed_event_count": 1, "rewrite_count": 0, "retry_count": 1, "latest_passed": False},
            ]
        }
    }
    out = pick_top_risk_sections(snapshot, limit=2)
    assert out == ["A", "C"]


def test_run_targeted_section_revisions_applies_selected_sections() -> None:
    client = _Client()
    text = "# T\n\n## A\n\nA body.\n\n## C\n\nC body.\n"
    snapshot = {
        "section_originality_hot_sample": {
            "rows": [
                {"title": "A", "failed_event_count": 2, "rewrite_count": 1, "retry_count": 0, "latest_passed": True},
                {"title": "C", "failed_event_count": 1, "rewrite_count": 0, "retry_count": 1, "latest_passed": False},
            ]
        }
    }
    updated, report = run_targeted_section_revisions(
        client=client,
        doc_id="doc-1",
        text=text,
        quality_snapshot=snapshot,
        max_sections=2,
    )
    assert "A rewritten body." in updated
    assert "C rewritten body." in updated
    assert report["attempted"] == 2
    assert report["applied"] == 2
    assert len(client.calls) == 2
    assert client.calls[0][1]["target_section"] == "A"
