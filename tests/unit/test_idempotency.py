import json
import time

from writing_agent.web.idempotency import IdempotencyStore, make_idempotency_key


def test_idempotency_store_roundtrip(tmp_path) -> None:
    store = IdempotencyStore(root=tmp_path)
    key = make_idempotency_key(doc_id="d1", route="generate", body={"instruction": "x"})
    store.put(key, {"ok": 1, "text": "t"})
    loaded = store.get(key)
    assert loaded is not None
    assert (loaded.get("payload") or {}).get("ok") == 1


def test_idempotency_store_ttl_expire_on_get(tmp_path) -> None:
    key = make_idempotency_key(doc_id="d1", route="generate", body={"instruction": "x"})
    store = IdempotencyStore(root=tmp_path, ttl_s=1, sweep_interval_s=0)
    store.put(key, {"ok": 1, "text": "t"})

    path = next(tmp_path.glob("*.json"))
    body = json.loads(path.read_text(encoding="utf-8"))
    body["saved_at"] = time.time() - 5
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2), encoding="utf-8")

    assert store.get(key) is None
    assert not path.exists()


def test_idempotency_store_eviction_by_max_entries(tmp_path) -> None:
    store = IdempotencyStore(root=tmp_path, ttl_s=3600, max_entries=2, sweep_interval_s=0)
    for i in range(3):
        key = make_idempotency_key(doc_id="d1", route="generate", body={"instruction": f"x-{i}"})
        store.put(key, {"ok": 1, "text": f"t-{i}"})

    files = list(tmp_path.glob("*.json"))
    assert len(files) <= 2
