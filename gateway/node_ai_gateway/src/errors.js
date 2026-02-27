export const ErrorCode = {
  BAD_REQUEST: 'BAD_REQUEST',
  RATE_LIMIT: 'RATE_LIMIT',
  TIMEOUT: 'TIMEOUT',
  CONTEXT_OVERFLOW: 'CONTEXT_OVERFLOW',
  SCHEMA_FAIL: 'SCHEMA_FAIL',
  PROVIDER_ERROR: 'PROVIDER_ERROR',
  INTERNAL_ERROR: 'INTERNAL_ERROR',
};

export function classifyError(error) {
  const status =
    Number(error?.statusCode ?? error?.status ?? error?.cause?.statusCode ?? error?.cause?.status ?? 0) || 0;
  const message = String(error?.message || 'unexpected gateway error');
  const lower = message.toLowerCase();

  if (status === 429 || (lower.includes('rate') && lower.includes('limit'))) {
    return { httpStatus: 429, code: ErrorCode.RATE_LIMIT, retryable: true, message: 'upstream rate limited' };
  }
  if (status === 408 || status === 504 || lower.includes('timeout') || lower.includes('timed out')) {
    return { httpStatus: 504, code: ErrorCode.TIMEOUT, retryable: true, message: 'upstream timeout' };
  }
  if (lower.includes('context') && (lower.includes('overflow') || lower.includes('length') || lower.includes('token'))) {
    return { httpStatus: 400, code: ErrorCode.CONTEXT_OVERFLOW, retryable: false, message: 'context length exceeded' };
  }
  if (lower.includes('schema') || lower.includes('json')) {
    return { httpStatus: 422, code: ErrorCode.SCHEMA_FAIL, retryable: false, message: 'schema validation failed' };
  }
  if (status >= 400 && status < 500) {
    return { httpStatus: status, code: ErrorCode.BAD_REQUEST, retryable: false, message: 'bad request' };
  }
  if (status >= 500) {
    return { httpStatus: status, code: ErrorCode.PROVIDER_ERROR, retryable: true, message: 'upstream provider error' };
  }
  return { httpStatus: 500, code: ErrorCode.INTERNAL_ERROR, retryable: false, message: 'internal gateway error' };
}

export function buildErrorPayload(classified, { traceId, latencyMs, provider, model }) {
  return {
    ok: 0,
    error: {
      code: classified.code,
      message: classified.message,
      retryable: Boolean(classified.retryable),
    },
    trace_id: traceId,
    provider,
    model,
    latency_ms: latencyMs,
  };
}
