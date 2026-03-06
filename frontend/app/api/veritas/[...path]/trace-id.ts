const TRACE_ID_PATTERN = /^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$/;

export const TRACE_ID_HEADER_NAME = "X-Trace-Id";

/**
 * Resolve trace id from incoming headers or generate a fresh id.
 *
 * Security:
 * - Rejects malformed user-supplied values to prevent log/header injection.
 * - Falls back to a cryptographically random UUID when unavailable.
 */
export function resolveTraceId(headers: Headers): string {
  const candidates = [
    headers.get(TRACE_ID_HEADER_NAME),
    headers.get("x-trace-id"),
    headers.get("X-Request-Id"),
    headers.get("x-request-id"),
  ];

  for (const candidate of candidates) {
    const normalized = (candidate ?? "").trim();
    if (TRACE_ID_PATTERN.test(normalized)) {
      return normalized;
    }
  }

  return crypto.randomUUID();
}
