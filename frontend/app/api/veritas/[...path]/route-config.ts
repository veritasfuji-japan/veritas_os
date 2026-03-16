/**
 * Resolve backend API base URL for BFF proxy requests.
 *
 * Security note:
 * - Intentionally ignores NEXT_PUBLIC_* env vars to avoid exposing or
 *   depending on browser-visible configuration for server-to-server calls.
 * - In production (`VERITAS_ENV=prod|production`), fail closed when
 *   `VERITAS_API_BASE_URL` is missing instead of silently using localhost.
 */
export function resolveApiBaseUrl(): string | null {
  const apiBaseUrl = process.env.VERITAS_API_BASE_URL?.trim();
  if (apiBaseUrl) {
    return apiBaseUrl;
  }

  const veritasEnv = (process.env.VERITAS_ENV ?? "").trim().toLowerCase();
  const isProduction = veritasEnv === "prod" || veritasEnv === "production";
  if (isProduction) {
    return null;
  }

  return "http://localhost:8000";
}
