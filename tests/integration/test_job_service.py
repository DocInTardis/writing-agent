from writing_agent.web.services.job_service import JobService


def test_job_service_submit_and_poll(tmp_path) -> None:
    svc = JobService(persist_path=tmp_path / 'jobs.json')
    row = svc.submit(job_type='generate', payload={'x': 1})
    assert row.status == 'queued'
    loaded = svc.get(row.job_id)
    assert loaded is not None
    svc.mark_done(row.job_id, {'ok': 1, 'text': 'done'})
    done = svc.get(row.job_id)
    assert done is not None and done.status == 'done'
    assert done.result and done.result.get('ok') == 1
