const cspReportOnly = [
  "default-src 'self'",
  "base-uri 'self'",
  "frame-ancestors 'none'",
  "object-src 'none'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self' data:",
  "connect-src 'self'",
  "form-action 'self'",
  "upgrade-insecure-requests",
  "block-all-mixed-content"
].join('; ');

/**
 * Returns baseline security headers for all routes.
 *
 * CSP is introduced in report-only mode first so we can audit violations
 * before switching to enforce mode.
 */
function getSecurityHeaders() {
  return [
    {
      key: 'Content-Security-Policy-Report-Only',
      value: cspReportOnly
    },
    {
      key: 'X-Frame-Options',
      value: 'DENY'
    },
    {
      key: 'Referrer-Policy',
      value: 'strict-origin-when-cross-origin'
    },
    {
      key: 'Permissions-Policy',
      value: 'camera=(), microphone=(), geolocation=()'
    },
    {
      key: 'Strict-Transport-Security',
      value: 'max-age=31536000; includeSubDomains; preload'
    },
    {
      key: 'X-Content-Type-Options',
      value: 'nosniff'
    }
  ];
}

/** @type {import('next').NextConfig} */
const nextConfig = {
  transpilePackages: ['@veritas/design-system', '@veritas/types'],
  async headers() {
    return [
      {
        source: '/:path*',
        headers: getSecurityHeaders()
      }
    ];
  }
};

export default nextConfig;
