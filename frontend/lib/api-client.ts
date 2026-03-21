/**
 * Shared BFF API client for `/api/veritas/*` endpoints.
 *
 * Authentication is handled via an httpOnly session cookie
 * (`__veritas_bff`) set by Next.js middleware on every page load.
 * The cookie is automatically included by the browser — no
 * client-side token handling is needed.
 *
 * All browser-side fetch calls to `/api/veritas/*` should use
 * {@link veritasFetch} instead of raw `fetch` so that timeout,
 * credential handling, error classification, and retry are consistent.
 */

"use client";

const DEFAULT_TIMEOUT_MS = 20_000;
const DEFAULT_RETRY_COUNT = 0;
const RETRYABLE_STATUS_CODES = new Set([502, 503, 504]);
const RETRY_BACKOFF_BASE_MS = 1_000;

/* ------------------------------------------------------------------ */
/*  Error classification                                               */
/* ------------------------------------------------------------------ */

export type ApiErrorKind =
  | "network"
  | "timeout"
  | "cancelled"
  | "auth"
  | "validation"
  | "server"
  | "unknown";

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status: number | null;
  readonly traceId: string | null;

  constructor(
    message: string,
    kind: ApiErrorKind,
    status: number | null = null,
    traceId: string | null = null,
  ) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
    this.traceId = traceId;
  }
}

export function classifyHttpStatus(status: number): ApiErrorKind {
  if (status === 401 || status === 403) return "auth";
  if (status === 400 || status === 422) return "validation";
  if (status >= 500) return "server";
  return "unknown";
}

/* ------------------------------------------------------------------ */
/*  Lightweight debug logger                                           */
/* ------------------------------------------------------------------ */

const IS_DEV =
  typeof process !== "undefined" && process.env.NODE_ENV === "development";

export function devLog(
  level: "info" | "warn" | "error",
  context: string,
  detail: Record<string, unknown>,
): void {
  if (!IS_DEV) return;
  const prefix = `[veritas:${context}]`;
  if (level === "error") {
    console.error(prefix, detail);
  } else if (level === "warn") {
    console.warn(prefix, detail);
  } else {
    console.info(prefix, detail);
  }
}

/* ------------------------------------------------------------------ */
/*  Core fetch wrapper                                                 */
/* ------------------------------------------------------------------ */

export interface VeritasFetchOptions {
  /** Request init passed to fetch. */
  init?: RequestInit;
  /** Timeout in ms (default 20 000). */
  timeoutMs?: number;
  /** Number of automatic retries for transient errors (default 0). */
  retries?: number;
}

/**
 * Wrapper around `fetch` that:
 * 1. Sets `credentials: "same-origin"` so the httpOnly session
 *    cookie is included automatically.
 * 2. Applies an AbortController-based timeout (default 20 s).
 *
 * NOTE: This function preserves the original error behavior
 * (throws DOMException on abort/timeout) for backward compatibility.
 * Use {@link veritasFetchWithOptions} for classified errors and retry.
 */
export async function veritasFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
  timeoutMs = DEFAULT_TIMEOUT_MS,
): Promise<Response> {
  const controller = new AbortController();
  // If the caller already has a signal, chain abort
  if (init.signal) {
    init.signal.addEventListener("abort", () => controller.abort(), {
      once: true,
    });
  }
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

  try {
    return await fetch(input, {
      ...init,
      credentials: "same-origin",
      signal: controller.signal,
    });
  } finally {
    clearTimeout(timeoutId);
  }
}

export async function veritasFetchWithOptions(
  input: RequestInfo | URL,
  options: VeritasFetchOptions = {},
): Promise<Response> {
  const {
    init = {},
    timeoutMs = DEFAULT_TIMEOUT_MS,
    retries = DEFAULT_RETRY_COUNT,
  } = options;

  let lastError: unknown = null;
  const maxAttempts = 1 + Math.max(0, retries);

  for (let attempt = 0; attempt < maxAttempts; attempt++) {
    const controller = new AbortController();
    let timedOut = false;
    // If the caller already has a signal, chain abort
    if (init.signal) {
      init.signal.addEventListener(
        "abort",
        () => controller.abort(init.signal?.reason),
        { once: true },
      );
    }
    const timeoutId = setTimeout(() => {
      timedOut = true;
      controller.abort(new DOMException("Request timed out", "TimeoutError"));
    }, timeoutMs);

    try {
      const response = await fetch(input, {
        ...init,
        credentials: "same-origin",
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      // Retry transient server errors
      if (
        RETRYABLE_STATUS_CODES.has(response.status) &&
        attempt < maxAttempts - 1
      ) {
        devLog("warn", "api-client", {
          event: "retry",
          url: String(input),
          status: response.status,
          attempt: attempt + 1,
        });
        await delay(RETRY_BACKOFF_BASE_MS * 2 ** attempt);
        continue;
      }

      return response;
    } catch (caught: unknown) {
      clearTimeout(timeoutId);
      lastError = caught;

      if (caught instanceof DOMException && caught.name === "AbortError") {
        if (timedOut) {
          throw new ApiError("Request timed out", "timeout", null, null);
        }
        if (init.signal?.aborted) {
          throw new ApiError("Request was cancelled", "cancelled", null, null);
        }
      }

      // Network errors are retryable
      if (attempt < maxAttempts - 1) {
        devLog("warn", "api-client", {
          event: "retry-network",
          url: String(input),
          attempt: attempt + 1,
          error: String(caught),
        });
        await delay(RETRY_BACKOFF_BASE_MS * 2 ** attempt);
        continue;
      }
    }
  }

  throw new ApiError(
    lastError instanceof Error ? lastError.message : "Network error",
    "network",
    null,
    null,
  );
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
