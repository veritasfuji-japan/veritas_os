/**
 * Shared BFF API client for `/api/veritas/*` endpoints.
 *
 * Authentication is handled via an httpOnly session cookie
 * (`__veritas_bff`) set by Next.js middleware on every page load.
 * The cookie is automatically included by the browser — no
 * client-side token handling is needed.
 *
 * All browser-side fetch calls to `/api/veritas/*` should use
 * {@link veritasFetch} instead of raw `fetch` so that timeout
 * and credential handling are consistent.
 */

const DEFAULT_TIMEOUT_MS = 20_000;

/**
 * Wrapper around `fetch` that:
 * 1. Sets `credentials: "same-origin"` so the httpOnly session
 *    cookie is included automatically.
 * 2. Applies an AbortController-based timeout (default 20 s).
 */
export async function veritasFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
  timeoutMs = DEFAULT_TIMEOUT_MS,
): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);

  try {
    return await fetch(input, {
      ...init,
      credentials: "same-origin",
      signal: controller.signal,
    });
  } finally {
    window.clearTimeout(timeoutId);
  }
}
