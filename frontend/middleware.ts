import { NextResponse, type NextRequest } from 'next/server';

const NONCE_BYTES = 16;

/**
 * Generates a CSP nonce for the current response.
 */
export function generateNonce(): string {
  return Buffer.from(crypto.getRandomValues(new Uint8Array(NONCE_BYTES))).toString('base64');
}

/**
 * Builds a strict CSP policy string bound to a nonce.
 */
export function buildCspWithNonce(nonce: string): string {
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
 */
export function middleware(_request: NextRequest): NextResponse {
  const nonce = generateNonce();
  const csp = buildCspWithNonce(nonce);
  const response = NextResponse.next();

  response.headers.set('x-veritas-nonce', nonce);
  response.headers.set('Content-Security-Policy', csp);
  response.headers.set('Content-Security-Policy-Report-Only', csp);

  return response;
}

export const config = {
  matcher: '/:path*'
};
