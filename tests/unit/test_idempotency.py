from writing_agent.web.idempotency import IdempotencyStore, make_idempotency_key


def test_idempotency_store_roundtrip(tmp_path) -> None:
    store = IdempotencyStore(root=tmp_path)
    key = make_idempotency_key(doc_id='d1', route='generate', body={'instruction': 'x'})
    store.put(key, {'ok': 1, 'text': 't'})
    loaded = store.get(key)
    assert loaded is not None
    assert (loaded.get('payload') or {}).get('ok') == 1
