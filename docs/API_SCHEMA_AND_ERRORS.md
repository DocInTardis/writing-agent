# API Schema And Error Codes

Canonical schema models are defined in:

- `writing_agent/web/contracts.py`

Error code enum:

- `BAD_REQUEST`
- `NOT_FOUND`
- `CONFLICT`
- `FORBIDDEN`
- `INTERNAL_ERROR`
- `TIMEOUT`

All new v1 endpoints should return `ok` + typed payload or `APIError`.
