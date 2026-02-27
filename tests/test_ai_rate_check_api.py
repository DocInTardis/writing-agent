from __future__ import annotations

from fastapi.testclient import TestClient

import writing_agent.web.app_v2 as app_v2


def _new_doc(text: str):
    session = app_v2.store.create()
    app_v2._set_doc_text(session, text)
    app_v2.store.put(session)
    return session


def test_ai_rate_check_requires_non_empty_doc():
    session = _new_doc("")
    client = TestClient(app_v2.app)
    resp = client.post(f"/api/doc/{session.id}/ai_rate/check", json={})
    assert resp.status_code == 400


def test_ai_rate_check_and_latest_endpoint():
    high_like = _new_doc(
        "首先，本方案将从目标、路径、执行三个方面展开。"
        "其次，本方案将从目标、路径、执行三个方面展开。"
        "再次，本方案将从目标、路径、执行三个方面展开。"
        "最后，本方案将从目标、路径、执行三个方面展开。"
        "首先，本方案将从目标、路径、执行三个方面展开。"
        "其次，本方案将从目标、路径、执行三个方面展开。"
        "再次，本方案将从目标、路径、执行三个方面展开。"
        "最后，本方案将从目标、路径、执行三个方面展开。"
        "首先，本方案将从目标、路径、执行三个方面展开。"
        "其次，本方案将从目标、路径、执行三个方面展开。"
    )
    low_like = _new_doc(
        "昨晚下雨，地面一直湿到早晨。"
        "我出门时差点滑倒，索性绕到小路。"
        "巷口卖豆浆的摊主刚支起棚子，热气混着雨味，闻起来很像小时候。"
        "我到公司时同事正在讨论产品上线计划，有人担心库存数据会延迟，有人则建议先做灰度。"
        "午后天放晴了，窗外有施工声，会议里不断有人进出，记录也比平时零散。"
        "晚上回家时地铁临时慢行，我顺手把白天的待办重新排了一遍。"
    )
    client = TestClient(app_v2.app)

    resp_high = client.post(
        f"/api/doc/{high_like.id}/ai_rate/check",
        json={"threshold": 0.6},
    )
    assert resp_high.status_code == 200
    high = resp_high.json()
    assert high.get("ok") == 1
    assert 0.0 <= float(high.get("ai_rate") or 0.0) <= 1.0
    assert isinstance(high.get("signals"), dict)

    resp_low = client.post(
        f"/api/doc/{low_like.id}/ai_rate/check",
        json={"threshold": 0.6},
    )
    assert resp_low.status_code == 200
    low = resp_low.json()
    assert low.get("ok") == 1
    assert 0.0 <= float(low.get("ai_rate") or 0.0) <= 1.0
    assert float(high.get("ai_rate") or 0.0) > float(low.get("ai_rate") or 0.0)

    latest = client.get(f"/api/doc/{high_like.id}/ai_rate/latest")
    assert latest.status_code == 200
    latest_body = latest.json()
    assert latest_body.get("has_latest") is True
    latest_payload = latest_body.get("latest") or {}
    assert float(latest_payload.get("ai_rate") or 0.0) == float(high.get("ai_rate") or 0.0)
