from __future__ import annotations

import os
from pathlib import Path

from scripts import report_support


def test_load_json_helpers_support_dict_list_and_invalid_payloads(tmp_path: Path) -> None:
    dict_path = tmp_path / "dict.json"
    list_path = tmp_path / "list.json"
    invalid_path = tmp_path / "invalid.json"

    dict_path.write_text('{"ok": true}', encoding="utf-8")
    list_path.write_text('[{"row": 1}]', encoding="utf-8")
    invalid_path.write_text('"scalar"', encoding="utf-8")

    assert report_support.load_json(dict_path) == {"ok": True}
    assert report_support.load_json(list_path) == [{"row": 1}]
    assert report_support.load_json(invalid_path) is None
    assert report_support.load_json_dict(dict_path) == {"ok": True}
    assert report_support.load_json_dict(list_path) == {}
    assert report_support.load_json_dict_or_none(dict_path) == {"ok": True}
    assert report_support.load_json_dict_or_none(list_path) is None


def test_latest_report_returns_newest_match(tmp_path: Path) -> None:
    older = tmp_path / "report_1.json"
    newer = tmp_path / "report_2.json"
    older.write_text("{}", encoding="utf-8")
    newer.write_text("{}", encoding="utf-8")
    os.utime(older, (1000, 1000))
    os.utime(newer, (2000, 2000))

    assert report_support.latest_report("report_*.json", root=tmp_path) == newer
    assert report_support.latest_report((tmp_path / "report_*.json").as_posix()) == newer


def test_event_helpers_normalize_rows_and_pick_latest_text() -> None:
    rows = [
        {"status": "old", "summary": ""},
        {"status": "new", "summary": "latest summary"},
        "ignored",
    ]

    assert report_support.normalize_events(rows) == rows[:2]
    assert report_support.normalize_events({"events": rows}) == rows[:2]
    assert report_support.normalize_events({"events": "bad"}) == []
    assert report_support.latest_text_field(rows[:2], "summary") == "latest summary"
    assert report_support.latest_text_field(rows[:2], "missing") == ""
    assert report_support.safe_float("3.5") == 3.5
    assert report_support.safe_float("bad", 2.0) == 2.0
    assert report_support.safe_int("4") == 4
    assert report_support.safe_int("bad", 7) == 7


def test_check_row_supports_keyword_and_positional_calls() -> None:
    keyword_row = report_support.check_row(
        check_id="keyword",
        ok=True,
        value=1,
        expect="ok",
        mode="warn",
    )
    positional_row = report_support.check_row("positional", False, 2, "expect", "enforce")

    assert keyword_row == {
        "id": "keyword",
        "ok": True,
        "value": 1,
        "expect": "ok",
        "mode": "warn",
    }
    assert positional_row == {
        "id": "positional",
        "ok": False,
        "value": 2,
        "expect": "expect",
        "mode": "enforce",
    }
