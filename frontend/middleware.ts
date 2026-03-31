import { NextResponse, type NextRequest } from "next/server";

const NONCE_BYTES = 16;
const ENFORCE_NONCE_ENV = "VERITAS_CSP_ENFORCE_NONCE";
const ALLOW_UNSAFE_INLINE_COMPAT_ENV = "VERITAS_CSP_ALLOW_UNSAFE_INLINE_COMPAT";
const REPORT_ONLY_ENDPOINT_ENV = "VERITAS_CSP_REPORT_ONLY_ENDPOINT";

/**
 * Generates a CSP nonce for the current response.
 */
export function generateNonce(): string {
  return Buffer.from(
    crypto.getRandomValues(new Uint8Array(NONCE_BYTES)),
  ).toString("base64");
}

/**
 * Returns whether enforced CSP should require script nonce tokens.
 *
 * Security behavior:
 * - Strict nonce CSP is enabled by explicit rollout flag.
 * - VERITAS production profile enforces nonce CSP by default in a fail-closed mode.
 * - Compatibility mode can be re-enabled only through
 *   VERITAS_CSP_ALLOW_UNSAFE_INLINE_COMPAT=true as a temporary migration escape hatch.
 * - NODE_ENV=production alone remains warning-only to avoid accidental rollout
 *   in environments that have not completed nonce compatibility validation.
 */
export function shouldEnforceNonceCsp(): boolean {
  if (process.env[ALLOW_UNSAFE_INLINE_COMPAT_ENV] === "true") {
    return false;
  }

  const veritasEnv = (process.env.VERITAS_ENV ?? "").toLowerCase();
  if (veritasEnv === "prod" || veritasEnv === "production") {
    return true;
  }

  return process.env[ENFORCE_NONCE_ENV] === "true";
}

/**
 * Returns whether runtime should emit a security warning for CSP rollout.
 *
 * Warns when:
 * - production runtime explicitly re-enables unsafe-inline via escape hatch, or
 * - NODE_ENV=production is used without strict nonce rollout.
 */
export function shouldWarnInsecureProductionCspConfig(): boolean {
  const veritasEnv = (process.env.VERITAS_ENV ?? "").toLowerCase();
  const nodeEnv = (process.env.NODE_ENV ?? "").toLowerCase();
  const isVeritasProductionRuntime =
    veritasEnv === "prod" ||
    veritasEnv === "production";
  const isNodeProductionRuntime = nodeEnv === "production";

  if (
    (isVeritasProductionRuntime || isNodeProductionRuntime) &&
    process.env[ALLOW_UNSAFE_INLINE_COMPAT_ENV] === "true"
  ) {
    return true;
  }

  return (
    isNodeProductionRuntime &&
    !isVeritasProductionRuntime &&
    process.env[ENFORCE_NONCE_ENV] !== "true"
  );
}

/**
 * Returns whether report-only CSP endpoint config is security-risky.
 *
 * Warns when:
 * - `VERITAS_CSP_REPORT_ONLY_ENDPOINT` is configured, and
 * - the configured endpoint is not a same-origin relative path.
 */
export function shouldWarnInsecureCspReportOnlyEndpoint(): boolean {
  const configuredEndpoint = (process.env[REPORT_ONLY_ENDPOINT_ENV] ?? "").trim();
  if (!configuredEndpoint) {
    return false;
  }
  return !configuredEndpoint.startsWith("/");
}

/**
 * Builds an enforced CSP policy string.
 *
 * Compatibility mode keeps `unsafe-inline` for scripts to avoid blocking
 * framework inline bootstrap scripts. Strict mode switches to nonce-based
 * script execution and is intended for phased rollout after runtime validation.
 */
export function buildCspEnforced(nonce: string, enforceNonce: boolean): string {
  const scriptDirective = enforceNonce
    ? `script-src 'self' 'nonce-${nonce}'`
    : "script-src 'self' 'unsafe-inline'";

  return [
    "default-src 'self'",
    "base-uri 'self'",
    "frame-ancestors 'none'",
    "object-src 'none'",
    scriptDirective,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self' data:",
    "connect-src 'self'",
    "form-action 'self'",
    "upgrade-insecure-requests",
    "block-all-mixed-content",
  ].join("; ");
}

/**
 * Builds a strict report-only CSP policy string bound to a nonce.
 */
export function buildCspReportOnly(nonce: string): string {
  const reportOnlyEndpoint = resolveCspReportOnlyEndpoint();

  return [
    "default-src 'self'",
    "base-uri 'self'",
    "frame-ancestors 'none'",
    "object-src 'none'",
    `script-src 'self' 'nonce-${nonce}'`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self' data:",
    "connect-src 'self'",
    "form-action 'self'",
    `report-uri ${reportOnlyEndpoint}`,
    "upgrade-insecure-requests",
    "block-all-mixed-content",
  ].join("; ");
}

/**
 * Resolves the CSP report-only collection endpoint.
 *
 * Security behavior:
 * - Defaults to same-origin `/api/veritas/csp-report` to keep violation reports
 *   within the BFF boundary.
 * - Allows explicit override through `VERITAS_CSP_REPORT_ONLY_ENDPOINT`.
 * - Falls back to the safe default when the override is empty.
 */
export function resolveCspReportOnlyEndpoint(): string {
  const configuredEndpoint = process.env[REPORT_ONLY_ENDPOINT_ENV] ?? "";
  const normalizedEndpoint = configuredEndpoint.trim();
  if (normalizedEndpoint) {
    return normalizedEndpoint;
  }
  return "/api/veritas/csp-report";
}

/**
 * Name of the httpOnly cookie used for BFF session auth.
 * Must match the constant in route-auth.ts.
 */
const BFF_SESSION_COOKIE = "__veritas_bff";

/**
 * Server-side env var holding the default BFF token for browser sessions.
 * This token must be a key present in VERITAS_BFF_AUTH_TOKENS_JSON.
 */
const BFF_SESSION_TOKEN_ENV = "VERITAS_BFF_SESSION_TOKEN";

/**
 * Attaches nonce-based CSP headers and BFF session cookie for every request.
 *
 * The nonce is forwarded through the internal `x-nonce` request header so
 * Next.js can annotate nonce-aware script tags where supported without
 * exposing the nonce back to browsers.
 *
 * The BFF session cookie provides same-origin authentication for browser
 * requests to `/api/veritas/*` without exposing tokens in client bundles.
 */
export function middleware(request: NextRequest): NextResponse {
  if (shouldWarnInsecureProductionCspConfig()) {
    console.warn(
      "[security-warning] CSP strict nonce rollout is not fully enforced for this production runtime. " +
        "Unset VERITAS_CSP_ALLOW_UNSAFE_INLINE_COMPAT and set VERITAS_ENV=production " +
        "(or VERITAS_CSP_ENFORCE_NONCE=true) after compatibility validation.",
    );
  }
  if (shouldWarnInsecureCspReportOnlyEndpoint()) {
    console.warn(
      "[security-warning] VERITAS_CSP_REPORT_ONLY_ENDPOINT is not a same-origin relative path. " +
        "External CSP report collectors may leak URL metadata and should be used only with explicit " +
        "data handling approval.",
    );
  }

  const nonce = generateNonce();
  const cspEnforced = buildCspEnforced(nonce, shouldEnforceNonceCsp());
  const cspReportOnly = buildCspReportOnly(nonce);

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);

  const response = NextResponse.next({
    request: {
      headers: requestHeaders,
    },
  });

  response.headers.set("Content-Security-Policy", cspEnforced);
  response.headers.set("Content-Security-Policy-Report-Only", cspReportOnly);

  // Set httpOnly BFF session cookie when configured and not already present.
  const sessionToken = process.env[BFF_SESSION_TOKEN_ENV] ?? "";
  if (sessionToken && !request.cookies.get(BFF_SESSION_COOKIE)) {
    response.cookies.set(BFF_SESSION_COOKIE, sessionToken, {
      httpOnly: true,
      secure: request.nextUrl.protocol === "https:",
      sameSite: "strict",
      path: "/api/veritas",
    });
  }

  return response;
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon\\.ico).*)"],
};
