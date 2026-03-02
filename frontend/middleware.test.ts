import { describe, expect, it } from 'vitest';

import { buildCspWithNonce, generateNonce, middleware } from './middleware';

describe('middleware CSP', () => {
  it('generates a nonce string', () => {
    const nonce = generateNonce();

    expect(nonce.length).toBeGreaterThan(10);
  });

  it('builds nonce-based CSP without unsafe-inline in script-src', () => {
    const csp = buildCspWithNonce('sample-nonce');
    const scriptDirective = csp
      .split(';')
      .find((directive) => directive.trim().startsWith('script-src'));

    expect(csp).toContain("default-src 'self'");
    expect(scriptDirective).toContain("'nonce-sample-nonce'");
    expect(scriptDirective).not.toContain("'unsafe-inline'");
  });

  it('sets enforced and report-only CSP headers with per-request nonce', () => {
    const response = middleware({} as never);
    const csp = response.headers.get('Content-Security-Policy') ?? '';
    const cspReportOnly = response.headers.get('Content-Security-Policy-Report-Only') ?? '';
    const nonce = response.headers.get('x-veritas-nonce') ?? '';
    const scriptDirective = csp
      .split(';')
      .find((directive) => directive.trim().startsWith('script-src'));

    expect(nonce).not.toBe('');
    expect(csp).toContain(`'nonce-${nonce}'`);
    expect(scriptDirective).not.toContain("'unsafe-inline'");
    expect(cspReportOnly).toBe(csp);
  });
});
