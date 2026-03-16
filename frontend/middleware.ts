import { NextResponse, type NextRequest } from 'next/server';

const NONCE_BYTES = 16;
const ENFORCE_NONCE_ENV = 'VERITAS_CSP_ENFORCE_NONCE';

/**
 * Generates a CSP nonce for the current response.
 */
export function generateNonce(): string {
  return Buffer.from(crypto.getRandomValues(new Uint8Array(NONCE_BYTES))).toString('base64');
}

/**
 * Returns whether enforced CSP should require script nonce tokens.
 *
 * Security behavior:
 * - Strict nonce CSP is enabled by explicit rollout flag.
 * - Production override is scoped to VERITAS_ENV only so that generic
 *   NODE_ENV=production builds (for CI/E2E) do not unintentionally break
 *   Next.js bootstrap scripts before nonce compatibility validation completes.
 */
export function shouldEnforceNonceCsp(): boolean {
  const veritasEnv = (process.env.VERITAS_ENV ?? '').toLowerCase();
  if (veritasEnv === 'prod' || veritasEnv === 'production') {
    return true;
  }
  return process.env[ENFORCE_NONCE_ENV] === 'true';
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
    'upgrade-insecure-requests',
    'block-all-mixed-content'
  ].join('; ');
}

/**
 * Builds a strict report-only CSP policy string bound to a nonce.
 */
export function buildCspReportOnly(nonce: string): string {
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
    'upgrade-insecure-requests',
    'block-all-mixed-content'
  ].join('; ');
}

/**
 * Name of the httpOnly cookie used for BFF session auth.
 * Must match the constant in route-auth.ts.
 */
const BFF_SESSION_COOKIE = '__veritas_bff';

/**
 * Server-side env var holding the default BFF token for browser sessions.
 * This token must be a key present in VERITAS_BFF_AUTH_TOKENS_JSON.
 */
const BFF_SESSION_TOKEN_ENV = 'VERITAS_BFF_SESSION_TOKEN';

/**
 * Attaches nonce-based CSP headers and BFF session cookie for every request.
 *
 * The nonce is forwarded through `x-nonce` request header so Next.js can
 * annotate nonce-aware script tags where supported.
 *
 * The BFF session cookie provides same-origin authentication for browser
 * requests to `/api/veritas/*` without exposing tokens in client bundles.
 */
export function middleware(request: NextRequest): NextResponse {
  const nonce = generateNonce();
  const cspEnforced = buildCspEnforced(nonce, shouldEnforceNonceCsp());
  const cspReportOnly = buildCspReportOnly(nonce);

  const requestHeaders = new Headers(request.headers);
  requestHeaders.set('x-nonce', nonce);

  const response = NextResponse.next({
    request: {
      headers: requestHeaders
    }
  });

  response.headers.set('Content-Security-Policy', cspEnforced);
  response.headers.set('Content-Security-Policy-Report-Only', cspReportOnly);
  response.headers.set('x-veritas-nonce', nonce);

  // Set httpOnly BFF session cookie when configured and not already present.
  const sessionToken = process.env[BFF_SESSION_TOKEN_ENV] ?? '';
  if (sessionToken && !request.cookies.get(BFF_SESSION_COOKIE)) {
    response.cookies.set(BFF_SESSION_COOKIE, sessionToken, {
      httpOnly: true,
      secure: request.nextUrl.protocol === 'https:',
      sameSite: 'strict',
      path: '/api/veritas',
    });
  }

  return response;
}

export const config = {
  matcher: [
    '/((?!_next/static|_next/image|favicon\\.ico).*)',
  ],
};
