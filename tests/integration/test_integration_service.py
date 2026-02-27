from writing_agent.web.contracts import WebhookEvent
from writing_agent.web.services.integration_service import IntegrationService


def test_integration_service_publish_and_list(tmp_path) -> None:
    svc = IntegrationService(event_log=tmp_path / 'events.jsonl')
    payload = WebhookEvent(event_type='generation.completed', tenant_id='t1', payload={'doc_id': 'd1'})
    out = svc.publish_event(payload)
    assert out.get('ok') == 1
    listing = svc.list_events(limit=10, tenant_id='t1')
    assert listing.get('ok') == 1
    assert listing.get('items')
