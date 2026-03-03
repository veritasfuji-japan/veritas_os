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
 */
export function shouldEnforceNonceCsp(): boolean {
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
 * Attaches nonce-based CSP headers for every request.
 *
 * The nonce is also forwarded through `x-nonce` request header so Next.js can
 * annotate nonce-aware script tags where supported.
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

  response.headers.set('x-veritas-nonce', nonce);
  response.headers.set('Content-Security-Policy', cspEnforced);
  response.headers.set('Content-Security-Policy-Report-Only', cspReportOnly);

  return response;
}

export const config = {
  matcher: '/:path*'
};
