const csp = [
  "default-src 'self'",
  "base-uri 'self'",
  "frame-ancestors 'none'",
  "object-src 'none'",
  "script-src 'self' 'nonce-__VERITAS_NONCE__'",
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
 * CSP is enforced. Script execution is restricted to self plus nonce-based
 * scripts to prevent inline script injection.
 */
function getSecurityHeaders() {
  return [
    {
      key: 'Content-Security-Policy',
      value: csp
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
