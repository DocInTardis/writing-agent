# Async Job Queue

Long-running tasks can be executed with submit/poll/callback mode.

Endpoints:

- `POST /api/v1/jobs/submit`
- `GET /api/v1/jobs/{job_id}`
- `GET /api/v1/jobs`

This mode improves peak stability by decoupling client request timeout from long generation/export operations.
