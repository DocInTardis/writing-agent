from __future__ import annotations

import time

from fastapi.testclient import TestClient

import writing_agent.web.app_v2 as app_v2
from writing_agent.models import Citation
from writing_agent.storage import InMemoryStore


def test_persistent_store_roundtrip(tmp_path) -> None:
    store = InMemoryStore(persistence_dir=tmp_path)
    session = store.create()
    session.doc_text = "# Persistent Title\n\nBody"
    session.status = "ready"
    session.labels = ["Client A", "Q2"]
    session.owner = "Alice"
    session.priority = "high"
    session.due_at = time.time() + 86400
    session.citations = {
        "c1": Citation(key="c1", title="Persistent Citation", authors="Alice", year="2025", venue="Venue", url="https://x")
    }
    store.put(session)

    reloaded = InMemoryStore(persistence_dir=tmp_path)
    restored = reloaded.get(session.id)

    assert restored is not None
    assert restored.title == "Persistent Title"
    assert restored.doc_text == "# Persistent Title\n\nBody"
    assert restored.citations["c1"].title == "Persistent Citation"
    assert restored.status == "ready"
    assert restored.labels == ["Client A", "Q2"]
    assert restored.owner == "Alice"
    assert restored.priority == "high"
    assert restored.due_at > 0


def test_workspace_lifecycle_routes(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(app_v2, "store", InMemoryStore(persistence_dir=tmp_path))
    client = TestClient(app_v2.app)

    created = client.post("/api/workspaces/create")
    assert created.status_code == 200
    doc_id = created.json()["doc_id"]

    save_resp = client.post(f"/api/doc/{doc_id}/save", json={"text": "# Product Home\n\nThis is body text."})
    assert save_resp.status_code == 200
    detail = client.get(f"/api/doc/{doc_id}").json()
    assert detail["status"] == "writing"

    listed = client.get("/api/workspaces", params={"status": "active"})
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["title"] == "Product Home"

    updated = client.post(
        f"/api/workspaces/{doc_id}/update",
        json={
            "title": "Renamed Workspace",
            "labels": ["Client A", "Q2"],
            "owner": "Alice",
            "priority": "high",
            "due_date": "2030-01-15",
        },
    )
    assert updated.status_code == 200
    assert updated.json()["workspace"]["title"] == "Renamed Workspace"
    assert updated.json()["workspace"]["labels"] == ["Client A", "Q2"]
    assert updated.json()["workspace"]["owner"] == "Alice"
    assert updated.json()["workspace"]["priority"] == "high"
    assert updated.json()["workspace"]["due_at"] > 0

    detail_after_update = client.get(f"/api/doc/{doc_id}")
    assert detail_after_update.status_code == 200
    assert detail_after_update.json()["labels"] == ["Client A", "Q2"]
    assert detail_after_update.json()["owner"] == "Alice"
    assert detail_after_update.json()["priority"] == "high"
    assert detail_after_update.json()["due_at"] > 0

    filtered = client.get("/api/workspaces", params={"status": "active", "q": "renamed"})
    assert filtered.status_code == 200
    assert filtered.json()["total"] == 1
    assert filtered.json()["items"][0]["title"] == "Renamed Workspace"

    label_filtered = client.get("/api/workspaces", params={"status": "active", "label": "client a"})
    assert label_filtered.status_code == 200
    assert label_filtered.json()["total"] == 1
    assert label_filtered.json()["items"][0]["labels"] == ["Client A", "Q2"]

    owner_filtered = client.get("/api/workspaces", params={"status": "active", "owner": "alice"})
    assert owner_filtered.status_code == 200
    assert owner_filtered.json()["total"] == 1
    assert owner_filtered.json()["items"][0]["owner"] == "Alice"

    priority_filtered = client.get("/api/workspaces", params={"status": "active", "priority": "high"})
    assert priority_filtered.status_code == 200
    assert priority_filtered.json()["total"] == 1
    assert priority_filtered.json()["items"][0]["priority"] == "high"

    legacy_filtered = client.get("/api/docs/list", params={"status": "active", "q": "renamed"})
    assert legacy_filtered.status_code == 200
    assert legacy_filtered.json()["total"] == 1
    assert legacy_filtered.json()["docs"][0]["title"] == "Renamed Workspace"

    legacy_label_filtered = client.get("/api/docs/list", params={"status": "active", "label": "client a"})
    assert legacy_label_filtered.status_code == 200
    assert legacy_label_filtered.json()["total"] == 1
    assert legacy_label_filtered.json()["docs"][0]["labels"] == ["Client A", "Q2"]

    legacy_owner_filtered = client.get("/api/docs/list", params={"status": "active", "owner": "alice", "priority": "high"})
    assert legacy_owner_filtered.status_code == 200
    assert legacy_owner_filtered.json()["total"] == 1
    assert legacy_owner_filtered.json()["docs"][0]["owner"] == "Alice"
    assert legacy_owner_filtered.json()["docs"][0]["priority"] == "high"

    duplicate = client.post(f"/api/workspaces/{doc_id}/duplicate")
    assert duplicate.status_code == 200
    duplicate_id = duplicate.json()["doc_id"]
    assert duplicate_id != doc_id
    assert duplicate.json()["workspace"]["title"] == "Renamed Workspace (Copy)"

    duplicate_updated = client.post(
        f"/api/workspaces/{duplicate_id}/update",
        json={"title": "Alpha Workspace", "labels": ["Client B"], "owner": "Bob", "priority": "medium", "due_date": "2030-02-01"},
    )
    assert duplicate_updated.status_code == 200
    assert duplicate_updated.json()["workspace"]["labels"] == ["Client B"]
    assert duplicate_updated.json()["workspace"]["owner"] == "Bob"
    assert duplicate_updated.json()["workspace"]["priority"] == "medium"

    title_sorted = client.get("/api/workspaces", params={"status": "all", "sort": "title"})
    assert title_sorted.status_code == 200
    assert [item["title"] for item in title_sorted.json()["items"][:2]] == ["Alpha Workspace", "Renamed Workspace"]

    pinned = client.post(f"/api/workspaces/{doc_id}/pin")
    assert pinned.status_code == 200
    assert pinned.json()["workspace"]["pinned"] is True

    sorted_items = client.get("/api/workspaces", params={"status": "all"}).json()["items"]
    assert sorted_items[0]["doc_id"] == doc_id

    unpinned = client.post(f"/api/workspaces/{doc_id}/unpin")
    assert unpinned.status_code == 200
    assert unpinned.json()["workspace"]["pinned"] is False

    status_changed = client.post(f"/api/workspaces/{doc_id}/status", json={"status": "review"})
    assert status_changed.status_code == 200
    assert status_changed.json()["workspace"]["status"] == "review"

    review_only = client.get("/api/workspaces", params={"status": "review"})
    assert review_only.status_code == 200
    assert review_only.json()["total"] == 1

    activity = client.get("/api/workspaces/activity")
    assert activity.status_code == 200
    messages = [str(item.get("message") or "") for item in activity.json()["items"]]
    assert any("Saved content" in message for message in messages)
    assert any("Status set to review" in message for message in messages)

    summary = client.get("/api/workspaces/summary")
    assert summary.status_code == 200
    summary_body = summary.json()
    assert summary_body["total"] >= 1
    assert summary_body["status_counts"]["review"] >= 1
    assert summary_body["activity_total"] >= 1
    assert summary_body["label_count"] >= 2
    assert any(item["name"] == "Client A" for item in summary_body["top_labels"])

    archived = client.post(f"/api/workspaces/{doc_id}/archive")
    assert archived.status_code == 200
    assert archived.json()["workspace"]["archived"] is True

    active_after_archive = client.get("/api/workspaces", params={"status": "active"}).json()
    assert all(item["doc_id"] != doc_id for item in active_after_archive["items"])

    restored = client.post(f"/api/workspaces/{doc_id}/restore")
    assert restored.status_code == 200
    assert restored.json()["workspace"]["archived"] is False

    trashed = client.post(f"/api/workspaces/{doc_id}/trash")
    assert trashed.status_code == 200
    assert trashed.json()["workspace"]["trashed"] is True

    active_after_trash = client.get("/api/workspaces", params={"status": "active"}).json()
    assert all(item["doc_id"] != doc_id for item in active_after_trash["items"])

    trash_only = client.get("/api/workspaces", params={"status": "trashed"})
    assert trash_only.status_code == 200
    assert trash_only.json()["total"] == 1
    assert trash_only.json()["items"][0]["doc_id"] == doc_id
    assert trash_only.json()["items"][0]["status"] == "trashed"

    trashed_detail = client.get(f"/api/doc/{doc_id}")
    assert trashed_detail.status_code == 200
    assert trashed_detail.json()["trashed"] is True

    saved_view = client.post(
        "/api/workspace-views/create",
        json={"name": "Client A Review", "status": "trashed", "label": "Client A", "owner": "Alice", "priority": "high", "sort": "due"},
    )
    assert saved_view.status_code == 200
    assert any(item["name"] == "Client A Review" for item in saved_view.json()["items"])

    saved_view_list = client.get(
        "/api/workspace-views",
        params={"status": "trashed", "label": "Client A", "owner": "Alice", "priority": "high", "sort": "due"},
    )
    assert saved_view_list.status_code == 200
    custom_view = next(item for item in saved_view_list.json()["items"] if item["name"] == "Client A Review")
    assert custom_view["active"] is True
    assert custom_view["count"] == 1
    assert custom_view["owner"] == "Alice"
    assert custom_view["priority"] == "high"

    deleted_view = client.post(f"/api/workspace-views/{custom_view['id']}/delete")
    assert deleted_view.status_code == 200

    untrashed = client.post(f"/api/workspaces/{doc_id}/untrash")
    assert untrashed.status_code == 200
    assert untrashed.json()["workspace"]["trashed"] is False

    purged = client.post(f"/api/workspaces/{duplicate_id}/purge")
    assert purged.status_code == 200
    assert purged.json()["doc_id"] == duplicate_id

    deleted = client.post(f"/api/doc/{doc_id}/delete")
    assert deleted.status_code == 200


def test_auto_title_tracks_document_until_manually_renamed(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(app_v2, "store", InMemoryStore(persistence_dir=tmp_path))
    client = TestClient(app_v2.app)

    doc_id = client.post("/api/workspaces/create").json()["doc_id"]
    client.post(f"/api/doc/{doc_id}/save", json={"text": "# First Title\n\nBody"})
    first = client.get("/api/workspaces", params={"status": "active"}).json()["items"][0]
    assert first["title"] == "First Title"

    client.post(f"/api/doc/{doc_id}/save", json={"text": "# Second Title\n\nBody"})
    second = client.get("/api/workspaces", params={"status": "active"}).json()["items"][0]
    assert second["title"] == "Second Title"

    client.post(f"/api/workspaces/{doc_id}/update", json={"title": "Pinned Title"})
    client.post(f"/api/doc/{doc_id}/save", json={"text": "# Third Title\n\nBody"})
    pinned = client.get("/api/workspaces", params={"status": "active"}).json()["items"][0]
    assert pinned["title"] == "Pinned Title"


def test_root_dashboard_and_system_status(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(app_v2, "store", InMemoryStore(persistence_dir=tmp_path))
    client = TestClient(app_v2.app)

    created = client.post("/api/workspaces/create").json()
    doc_id = created["doc_id"]
    client.post(f"/api/doc/{doc_id}/save", json={"text": "# Dashboard Doc\n\nContent"})

    home = client.get("/", params={"q": "dashboard", "status": "all"})
    assert home.status_code == 200
    assert "Writing Agent Studio" in home.text
    assert "Dashboard Doc" in home.text
    assert "Search, filter, sort, assign owners" in home.text
    assert "Resume Latest" in home.text
    assert "Recent Activity" in home.text
    assert "Review Queue" in home.text
    assert "Assigned" in home.text
    assert "High Priority" in home.text
    assert "Batch Update" in home.text
    assert "Confirm Action" in home.text
    assert "Set status" in home.text
    assert "Rename Workspace" in home.text
    assert "Edit Workspace Labels" in home.text
    assert "Save current view" in home.text

    latest_workspace = client.get("/latest", follow_redirects=False)
    assert latest_workspace.status_code == 303
    assert (latest_workspace.headers.get("location") or "").endswith(doc_id)

    new_workspace = client.get("/new", follow_redirects=False)
    assert new_workspace.status_code == 303
    assert (new_workspace.headers.get("location") or "").startswith("/workbench/")

    health = client.get("/healthz")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    status = client.get("/api/system/status")
    assert status.status_code == 200
    payload = status.json()
    assert payload["ok"] == 1
    assert payload["workspaces"]["active"] >= 1
    assert payload["workspaces"]["trashed"] >= 0
    assert payload["workspace_dir"].endswith("workspaces")


def test_overdue_filters_saved_views_and_home_modal(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(app_v2, "store", InMemoryStore(persistence_dir=tmp_path))
    client = TestClient(app_v2.app)

    overdue_id = client.post("/api/workspaces/create").json()["doc_id"]
    future_id = client.post("/api/workspaces/create").json()["doc_id"]
    unassigned_id = client.post("/api/workspaces/create").json()["doc_id"]
    no_priority_id = client.post("/api/workspaces/create").json()["doc_id"]

    client.post(f"/api/doc/{overdue_id}/save", json={"text": "# Overdue Doc\n\nContent"})
    client.post(f"/api/doc/{future_id}/save", json={"text": "# Planned Doc\n\nContent"})
    client.post(f"/api/doc/{unassigned_id}/save", json={"text": "# Unassigned Doc\n\nContent"})
    client.post(f"/api/doc/{no_priority_id}/save", json={"text": "# No Priority Doc\n\nContent"})

    overdue_session = app_v2.store.get(overdue_id)
    future_session = app_v2.store.get(future_id)
    unassigned_session = app_v2.store.get(unassigned_id)
    no_priority_session = app_v2.store.get(no_priority_id)
    assert overdue_session is not None and future_session is not None and unassigned_session is not None and no_priority_session is not None

    overdue_session.owner = "Alice"
    overdue_session.priority = "high"
    overdue_session.due_at = time.time() - 3600
    app_v2.store.put(overdue_session)

    future_session.owner = "Bob"
    future_session.due_at = time.time() + 86400
    app_v2.store.put(future_session)

    no_priority_session.owner = "Carol"
    no_priority_session.due_at = 0.0
    app_v2.store.put(no_priority_session)

    overdue_items = client.get("/api/workspaces", params={"status": "active", "overdue": "1", "sort": "due"}).json()["items"]
    assert [item["doc_id"] for item in overdue_items] == [overdue_id]
    assert overdue_items[0]["overdue"] is True

    due_soon_items = client.get("/api/workspaces", params={"status": "active", "due_soon": "1", "sort": "due"}).json()["items"]
    assert [item["doc_id"] for item in due_soon_items] == [future_id]
    assert due_soon_items[0]["due_soon"] is True

    unassigned_items = client.get("/api/workspaces", params={"status": "active", "unassigned": "1"}).json()["items"]
    assert [item["doc_id"] for item in unassigned_items] == [unassigned_id]
    assert unassigned_items[0]["unassigned"] is True

    no_due_date_items = client.get("/api/workspaces", params={"status": "active", "no_due_date": "1"}).json()["items"]
    assert {item["doc_id"] for item in no_due_date_items} == {unassigned_id, no_priority_id}
    assert all(item["no_due_date"] is True for item in no_due_date_items)

    no_priority_items = client.get("/api/workspaces", params={"status": "active", "no_priority": "1"}).json()["items"]
    assert {item["doc_id"] for item in no_priority_items} == {future_id, unassigned_id, no_priority_id}
    assert all(item["no_priority"] is True for item in no_priority_items)

    legacy_overdue = client.get("/api/docs/list", params={"status": "active", "overdue": "1", "sort": "due"}).json()
    assert legacy_overdue["total"] == 1
    assert legacy_overdue["docs"][0]["doc_id"] == overdue_id
    assert legacy_overdue["docs"][0]["overdue"] is True

    legacy_due_soon = client.get("/api/docs/list", params={"status": "active", "due_soon": "1", "sort": "due"}).json()
    assert legacy_due_soon["total"] == 1
    assert legacy_due_soon["docs"][0]["doc_id"] == future_id
    assert legacy_due_soon["docs"][0]["due_soon"] is True

    legacy_unassigned = client.get("/api/docs/list", params={"status": "active", "unassigned": "1"}).json()
    assert legacy_unassigned["total"] == 1
    assert legacy_unassigned["docs"][0]["doc_id"] == unassigned_id
    assert legacy_unassigned["docs"][0]["unassigned"] is True

    legacy_no_due_date = client.get("/api/docs/list", params={"status": "active", "no_due_date": "1"}).json()
    assert legacy_no_due_date["total"] == 2
    assert {item["doc_id"] for item in legacy_no_due_date["docs"]} == {unassigned_id, no_priority_id}
    assert all(item["no_due_date"] is True for item in legacy_no_due_date["docs"])

    legacy_no_priority = client.get("/api/docs/list", params={"status": "active", "no_priority": "1"}).json()
    assert legacy_no_priority["total"] == 3
    assert {item["doc_id"] for item in legacy_no_priority["docs"]} == {future_id, unassigned_id, no_priority_id}
    assert all(item["no_priority"] is True for item in legacy_no_priority["docs"])

    saved_view = client.post(
        "/api/workspace-views/create",
        json={"name": "Late Work", "status": "active", "overdue": True, "sort": "due"},
    )
    assert saved_view.status_code == 200

    due_soon_view = client.post(
        "/api/workspace-views/create",
        json={"name": "Due Soon Work", "status": "active", "due_soon": True, "sort": "due"},
    )
    assert due_soon_view.status_code == 200

    unassigned_view = client.post(
        "/api/workspace-views/create",
        json={"name": "Unassigned Work", "status": "active", "unassigned": True, "sort": "updated"},
    )
    assert unassigned_view.status_code == 200

    no_due_date_view = client.post(
        "/api/workspace-views/create",
        json={"name": "No Due Date Work", "status": "active", "no_due_date": True, "sort": "updated"},
    )
    assert no_due_date_view.status_code == 200

    no_priority_view = client.post(
        "/api/workspace-views/create",
        json={"name": "No Priority Work", "status": "active", "no_priority": True, "sort": "updated"},
    )
    assert no_priority_view.status_code == 200

    saved_views = client.get("/api/workspace-views", params={"status": "active", "overdue": "1", "sort": "due"}).json()["items"]
    late_work = next(item for item in saved_views if item["name"] == "Late Work")
    assert late_work["active"] is True
    assert late_work["count"] == 1
    assert late_work["overdue"] is True

    due_soon_views = client.get("/api/workspace-views", params={"status": "active", "due_soon": "1", "sort": "due"}).json()["items"]
    due_soon_view_item = next(item for item in due_soon_views if item["name"] == "Due Soon Work")
    assert due_soon_view_item["active"] is True
    assert due_soon_view_item["count"] == 1
    assert due_soon_view_item["due_soon"] is True

    unassigned_views = client.get("/api/workspace-views", params={"status": "active", "unassigned": "1", "sort": "updated"}).json()["items"]
    unassigned_view_item = next(item for item in unassigned_views if item["name"] == "Unassigned Work")
    assert unassigned_view_item["active"] is True
    assert unassigned_view_item["count"] == 1
    assert unassigned_view_item["unassigned"] is True

    no_due_date_views = client.get("/api/workspace-views", params={"status": "active", "no_due_date": "1", "sort": "updated"}).json()["items"]
    no_due_date_view_item = next(item for item in no_due_date_views if item["name"] == "No Due Date Work")
    assert no_due_date_view_item["active"] is True
    assert no_due_date_view_item["count"] == 2
    assert no_due_date_view_item["no_due_date"] is True

    no_priority_views = client.get("/api/workspace-views", params={"status": "active", "no_priority": "1", "sort": "updated"}).json()["items"]
    no_priority_view_item = next(item for item in no_priority_views if item["name"] == "No Priority Work")
    assert no_priority_view_item["active"] is True
    assert no_priority_view_item["count"] == 3
    assert no_priority_view_item["no_priority"] is True

    home = client.get("/", params={"status": "active", "overdue": "1", "sort": "due"})
    assert home.status_code == 200
    assert "Overdue only" in home.text
    assert "Due Soon" in home.text
    assert "Unassigned" in home.text
    assert "No Due Date" in home.text
    assert "No Priority" in home.text
    assert "Workspace Details" in home.text


def test_workspace_batch_actions_and_expired_trash_cleanup(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(app_v2, "store", InMemoryStore(persistence_dir=tmp_path))
    client = TestClient(app_v2.app)

    doc_a = client.post("/api/workspaces/create").json()["doc_id"]
    doc_b = client.post("/api/workspaces/create").json()["doc_id"]

    resp = client.post(
        "/api/workspaces/batch",
        json={"doc_ids": [doc_a, doc_b], "action": "status", "status": "review"},
    )
    assert resp.status_code == 200
    assert resp.json()["count"] == 2

    review_items = client.get("/api/workspaces", params={"status": "review"}).json()["items"]
    assert {item["doc_id"] for item in review_items} == {doc_a, doc_b}

    trash_resp = client.post(
        "/api/workspaces/batch",
        json={"doc_ids": [doc_a, doc_b], "action": "trash"},
    )
    assert trash_resp.status_code == 200
    assert trash_resp.json()["count"] == 2

    trashed_items = client.get("/api/workspaces", params={"status": "trashed"}).json()["items"]
    assert {item["doc_id"] for item in trashed_items} == {doc_a, doc_b}

    add_labels_resp = client.post(
        "/api/workspaces/batch",
        json={"doc_ids": [doc_a, doc_b], "action": "labels_add", "labels": ["Ops", "Q3"]},
    )
    assert add_labels_resp.status_code == 200
    labeled_items = client.get("/api/workspaces", params={"status": "trashed", "label": "Ops"}).json()["items"]
    assert {item["doc_id"] for item in labeled_items} == {doc_a, doc_b}

    replace_labels_resp = client.post(
        "/api/workspaces/batch",
        json={"doc_ids": [doc_a], "action": "labels_replace", "labels": ["Client X"]},
    )
    assert replace_labels_resp.status_code == 200

    remove_labels_resp = client.post(
        "/api/workspaces/batch",
        json={"doc_ids": [doc_b], "action": "labels_remove", "labels": ["Ops"]},
    )
    assert remove_labels_resp.status_code == 200

    owner_set_resp = client.post(
        "/api/workspaces/batch",
        json={"doc_ids": [doc_a, doc_b], "action": "owner_set", "owner": "Ops Lead"},
    )
    assert owner_set_resp.status_code == 200

    priority_set_resp = client.post(
        "/api/workspaces/batch",
        json={"doc_ids": [doc_a, doc_b], "action": "priority_set", "priority": "urgent"},
    )
    assert priority_set_resp.status_code == 200

    due_set_resp = client.post(
        "/api/workspaces/batch",
        json={"doc_ids": [doc_a, doc_b], "action": "due_set", "due_date": "2030-03-01"},
    )
    assert due_set_resp.status_code == 200

    owner_priority_items = client.get("/api/workspaces", params={"status": "trashed", "owner": "ops lead", "priority": "urgent"}).json()["items"]
    assert {item["doc_id"] for item in owner_priority_items} == {doc_a, doc_b}

    session_a = app_v2.store.get(doc_a)
    session_b = app_v2.store.get(doc_b)
    assert session_a is not None and session_b is not None
    session_a.trashed = True
    session_a.trash_until = time.time() + 30
    app_v2.store.put(session_a)
    session_b = app_v2.store.get(doc_b)
    assert session_b is not None
    session_b.trashed = True
    session_b.trash_until = time.time() + 120
    app_v2.store.put(session_b)

    expires_sorted = client.get("/api/workspaces", params={"status": "trashed", "sort": "expires"}).json()["items"]
    assert [item["doc_id"] for item in expires_sorted[:2]] == [doc_a, doc_b]

    due_sorted = client.get("/api/workspaces", params={"status": "trashed", "sort": "due"}).json()["items"]
    assert [item["doc_id"] for item in due_sorted[:2]] == [doc_a, doc_b]

    session_b.trash_until = time.time() - 10
    app_v2.store.put(session_b)

    after_cleanup = client.get("/api/workspaces", params={"status": "all"}).json()["items"]
    assert {item["doc_id"] for item in after_cleanup} == {doc_a}
    assert app_v2.store.get(doc_b) is None

    restore_resp = client.post(
        "/api/workspaces/batch",
        json={"doc_ids": [doc_a], "action": "untrash"},
    )
    assert restore_resp.status_code == 200
    assert restore_resp.json()["count"] == 1
    assert client.get("/api/workspaces", params={"status": "active"}).json()["total"] == 1


def test_template_catalog_and_template_based_workspace_creation(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(app_v2, "store", InMemoryStore(persistence_dir=tmp_path))
    client = TestClient(app_v2.app)

    catalog = client.get("/api/workspaces/templates")
    assert catalog.status_code == 200
    items = catalog.json()["items"]
    assert items
    template_id = items[0]["id"]

    created = client.post("/api/workspaces/create", json={"template": template_id})
    assert created.status_code == 200
    doc_id = created.json()["doc_id"]

    loaded = client.get(f"/api/doc/{doc_id}")
    assert loaded.status_code == 200
    body = loaded.json()
    assert body["template_name"]
    assert body["template_outline"] or body["required_h2"] or body["text"]
    assert body["text"].startswith("# ")
