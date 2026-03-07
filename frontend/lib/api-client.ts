/**
 * Shared BFF API client that attaches the Authorization header
 * required by the BFF proxy (route-auth.ts).
 *
 * All browser-side fetch calls to `/api/veritas/*` should use
 * {@link veritasFetch} instead of raw `fetch` so that the Bearer
 * token is consistently included.
 */

const DEFAULT_TIMEOUT_MS = 20_000;

/**
 * Resolve the BFF bearer token exposed to the browser.
 *
 * The token is injected via `NEXT_PUBLIC_VERITAS_BFF_TOKEN` at build time.
 * Returns an empty string when not configured (dev / test).
 */
function getBffToken(): string {
  if (typeof window === "undefined") return "";
  return process.env.NEXT_PUBLIC_VERITAS_BFF_TOKEN ?? "";
}

/**
 * Wrapper around `fetch` that:
 * 1. Prepends `Authorization: Bearer <token>` when a BFF token is available.
 * 2. Applies an AbortController-based timeout (default 20 s).
 *
 * Callers can still pass their own `signal` via `init`; the timeout controller
 * will abort independently if the deadline is exceeded.
 */
export async function veritasFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
  timeoutMs = DEFAULT_TIMEOUT_MS,
): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);

  const token = getBffToken();
  const headers = new Headers(init.headers);
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  try {
    return await fetch(input, {
      ...init,
      headers,
      signal: controller.signal,
    });
  } finally {
    window.clearTimeout(timeoutId);
  }
}
