/**
 * Resolve backend API base URL for BFF proxy requests.
 *
 * Security note:
 * - Intentionally ignores NEXT_PUBLIC_* env vars to avoid exposing or
 *   depending on browser-visible configuration for server-to-server calls.
 * - In production (`VERITAS_ENV=prod|production`), fail closed when
 *   `VERITAS_API_BASE_URL` is missing instead of silently using localhost.
 */
let hasWarnedPublicApiBaseUrl = false;

function warnPublicApiBaseUrlEnvOnce(): void {
  if (hasWarnedPublicApiBaseUrl) {
    return;
  }

  const publicApiBaseUrl = process.env.NEXT_PUBLIC_VERITAS_API_BASE_URL?.trim();
  if (!publicApiBaseUrl) {
    return;
  }

  hasWarnedPublicApiBaseUrl = true;
  console.warn(
    "[security-warning] NEXT_PUBLIC_VERITAS_API_BASE_URL is set. " +
      "Use server-only VERITAS_API_BASE_URL for BFF routing.",
  );
}

function hasPublicApiBaseUrlEnv(): boolean {
  const publicApiBaseUrl = process.env.NEXT_PUBLIC_VERITAS_API_BASE_URL?.trim();
  return Boolean(publicApiBaseUrl);
}

export function resolveApiBaseUrl(): string | null {
  warnPublicApiBaseUrlEnvOnce();

  const apiBaseUrl = process.env.VERITAS_API_BASE_URL?.trim();
  const veritasEnv = (process.env.VERITAS_ENV ?? "").trim().toLowerCase();
  const nodeEnv = (process.env.NODE_ENV ?? "").trim().toLowerCase();
  const isProduction =
    veritasEnv === "prod" ||
    veritasEnv === "production" ||
    nodeEnv === "production";
  if (isProduction && hasPublicApiBaseUrlEnv()) {
    console.warn(
      "[security-warning] NEXT_PUBLIC_VERITAS_API_BASE_URL must be unset in production. " +
        "BFF routing is blocked until only VERITAS_API_BASE_URL is configured.",
    );
    return null;
  }

  if (apiBaseUrl) {
    return apiBaseUrl;
  }

  if (isProduction) {
    return null;
  }

  return "http://localhost:8000";
}

export function resetApiBaseUrlWarningStateForTest(): void {
  hasWarnedPublicApiBaseUrl = false;
}
