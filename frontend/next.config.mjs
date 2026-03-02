/**
 * Returns baseline non-CSP security headers for all routes.
 *
 * CSP headers are generated dynamically in middleware so a per-request nonce
 * can be attached to the strict Report-Only policy while enforced CSP remains
 * compatibility-focused.
 */
function getSecurityHeaders() {
  return [
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
