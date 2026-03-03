import { describe, expect, it } from 'vitest';

import {
  buildCspEnforced,
  buildCspReportOnly,
  generateNonce,
  middleware
} from './middleware';

describe('middleware CSP', () => {
  it('generates a nonce string', () => {
    const nonce = generateNonce();

    expect(nonce.length).toBeGreaterThan(10);
  });

  it('builds enforced CSP without unsafe-inline in script-src', () => {
    const csp = buildCspEnforced('sample-nonce');
    const scriptDirective = csp
      .split(';')
      .find((directive) => directive.trim().startsWith('script-src'));

    expect(csp).toContain("default-src 'self'");
    expect(scriptDirective).toContain("'nonce-sample-nonce'");
    expect(scriptDirective).not.toContain("'unsafe-inline'");
  });

  it('builds nonce-based report-only CSP without unsafe-inline in script-src', () => {
    const csp = buildCspReportOnly('sample-nonce');
    const scriptDirective = csp
      .split(';')
      .find((directive) => directive.trim().startsWith('script-src'));

    expect(csp).toContain("default-src 'self'");
    expect(scriptDirective).toContain("'nonce-sample-nonce'");
    expect(scriptDirective).not.toContain("'unsafe-inline'");
  });

  it('sets nonce-based enforced CSP and nonce-based report-only CSP headers', () => {
    const response = middleware({} as never);
    const csp = response.headers.get('Content-Security-Policy') ?? '';
    const cspReportOnly = response.headers.get('Content-Security-Policy-Report-Only') ?? '';
    const nonce = response.headers.get('x-veritas-nonce') ?? '';
    const scriptDirective = csp
      .split(';')
      .find((directive) => directive.trim().startsWith('script-src'));
    const reportOnlyScriptDirective = cspReportOnly
      .split(';')
      .find((directive) => directive.trim().startsWith('script-src'));

    expect(nonce).not.toBe('');
    expect(scriptDirective).toContain(`'nonce-${nonce}'`);
    expect(scriptDirective).not.toContain("'unsafe-inline'");
    expect(reportOnlyScriptDirective).toContain(`'nonce-${nonce}'`);
    expect(reportOnlyScriptDirective).not.toContain("'unsafe-inline'");
  });
});
