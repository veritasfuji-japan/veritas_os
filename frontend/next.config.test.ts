import { describe, expect, it } from 'vitest';

import nextConfig from './next.config.mjs';

describe('next.config headers', () => {
  it('defines baseline security headers for all routes', async () => {
    const routes = await nextConfig.headers?.();

    expect(routes).toBeDefined();
    expect(routes).toHaveLength(1);
    expect(routes?.[0]).toMatchObject({ source: '/:path*' });

    const headerMap = new Map(routes?.[0].headers.map((item) => [item.key, item.value]));

    expect(headerMap.get('Content-Security-Policy')).toContain("default-src 'self'");
    const cspHeader = headerMap.get('Content-Security-Policy') ?? '';
    const scriptDirective = cspHeader.split(';').find((directive) => directive.trim().startsWith('script-src')) ?? '';

    expect(scriptDirective).not.toContain("'unsafe-inline'");
    expect(headerMap.get('Content-Security-Policy')).toContain("'nonce-__VERITAS_NONCE__'");
    expect(headerMap.get('X-Frame-Options')).toBe('DENY');
    expect(headerMap.get('Referrer-Policy')).toBe('strict-origin-when-cross-origin');
    expect(headerMap.get('Permissions-Policy')).toContain('camera=()');
    expect(headerMap.get('Strict-Transport-Security')).toContain('max-age=31536000');
    expect(headerMap.get('X-Content-Type-Options')).toBe('nosniff');
  });
});
