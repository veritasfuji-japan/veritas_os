/**
 * Resolve backend API base URL for BFF proxy requests.
 *
 * Security note:
 * - Intentionally ignores NEXT_PUBLIC_* env vars to avoid exposing or
 *   depending on browser-visible configuration for server-to-server calls.
 */
export function resolveApiBaseUrl(): string {
  const apiBaseUrl = process.env.VERITAS_API_BASE_URL?.trim();
  if (apiBaseUrl) {
    return apiBaseUrl;
  }
  return "http://localhost:8000";
}
